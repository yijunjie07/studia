"""Exercise the real browser UI with slow and failing platform responses."""
import json
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

STATIC = Path(__file__).resolve().parents[1] / "web" / "static"
PLATFORMS = [
    {"id": "mooc", "name": "MOOC", "short": "MOOC", "login": "browser", "logged_in": True,
     "features": {"answer": False}},
    {"id": "zhs", "name": "智慧树", "short": "智慧树", "login": "qr", "logged_in": True,
     "features": {"answer": False, "qa": True}},
]
COURSE = {"id": "shared-1", "name": "课程", "type": "共享课", "kind": "shared", "progress": 0,
          "features": {"qa": True}, "shares": {"interactive": 10}}


class Fixture(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def log_message(self, *args):
        pass

    def do_GET(self):
        path = urlsplit(self.path).path
        if not path.startswith("/api/"):
            return super().do_GET()
        if path == "/api/events":
            self.send_response(204)
            self.end_headers()
            return
        if path == "/api/platforms/mooc/courses":
            self.server.course_requested.set()
            self.server.release_courses.wait(10)
        if path.endswith("/score"):
            self.server.score_requests += 1
            self.server.score_requested.set()
            self.server.release_score.wait(10)
            self.send_response(503)
            data = {"error": "成绩暂不可用"}
        else:
            self.send_response(200)
            data = {"/api/mode": {"mode": "local"},
                    "/api/state": {"platforms": PLATFORMS, "jobs": [], "history": []},
                    "/api/platforms/mooc/courses": {"courses": []},
                    "/api/platforms/zhs/courses": {"courses": [COURSE]},
                    "/api/platforms/zhs/qa": {"posts": [], "room": {"ask": 1, "answer": 1, "posted": {}}, "peers": False},
                    "/api/platforms/zhs/units": {"chapters": []}}.get(path, {})
        body = json.dumps(data).encode()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # the browser may navigate away while the delayed request is pending


class WebResponsivenessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        if not Path(cls.playwright.chromium.executable_path).exists():
            cls.playwright.stop()
            raise unittest.SkipTest("Playwright Chromium is not installed")
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
        self.server.course_requested = threading.Event()
        self.server.release_courses = threading.Event()
        self.server.score_requested = threading.Event()
        self.server.release_score = threading.Event()
        self.server.release_score.set()
        self.server.score_requests = 0
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.page = self.browser.new_page()
        self.base = "http://127.0.0.1:%d/?t=test" % self.server.server_port

    def tearDown(self):
        self.server.release_courses.set()
        self.server.release_score.set()
        self.page.close()
        self.server.shutdown()
        self.server.server_close()

    def test_settings_opens_while_another_platform_is_slow(self):
        self.page.goto(self.base + "#/settings/account", wait_until="domcontentloaded")
        self.assertTrue(self.server.course_requested.wait(3))
        self.page.get_by_role("heading", name="设置").wait_for(timeout=1500)

    def test_first_visit_shows_loading_page_while_current_platform_is_slow(self):
        self.page.goto(self.base + "#/settings/account", wait_until="domcontentloaded")
        self.assertTrue(self.server.course_requested.wait(3))
        self.page.evaluate("localStorage.setItem('studia-platform', JSON.stringify('mooc'))")
        self.page.goto(self.base, wait_until="domcontentloaded")
        self.page.get_by_role("heading", name="课程").wait_for(timeout=1500)
        self.page.get_by_text("正在读取课程…").first.wait_for(timeout=1500)

    def test_slow_start_does_not_replace_a_page_the_user_already_opened(self):
        self.page.add_init_script("localStorage.setItem('studia-platform', JSON.stringify('mooc'))")
        self.page.goto(self.base, wait_until="domcontentloaded")
        self.assertTrue(self.server.course_requested.wait(3))
        self.page.get_by_text("正在读取课程…").first.wait_for(timeout=1500)
        self.page.evaluate("location.hash = '#/settings/account'")
        heading = self.page.get_by_role("heading", name="设置").element_handle(timeout=1500)
        self.server.release_courses.set()
        self.page.wait_for_timeout(600)
        self.assertTrue(heading.evaluate("el => el.isConnected"))

    def test_failed_score_does_not_loop_and_retries_on_revisit(self):
        self.server.release_courses.set()
        self.page.goto(self.base + "#/course/zhs/shared-1/qa", wait_until="domcontentloaded")
        self.page.get_by_text("问答互动", exact=True).wait_for(timeout=3000)
        self.page.wait_for_timeout(1200)
        self.assertEqual(self.server.score_requests, 1)
        self.page.evaluate("location.hash = '#/home'")
        self.page.evaluate("location.hash = '#/course/zhs/shared-1/qa'")
        self.page.wait_for_timeout(700)
        self.assertEqual(self.server.score_requests, 2)

    def test_reentering_while_score_is_loading_retries_a_later_failure(self):
        self.server.release_courses.set()
        self.server.release_score.clear()
        self.page.goto(self.base + "#/course/zhs/shared-1/qa", wait_until="domcontentloaded")
        self.page.get_by_text("问答互动", exact=True).wait_for(timeout=3000)
        self.assertTrue(self.server.score_requested.wait(3))
        self.page.evaluate("location.hash = '#/home'")
        self.page.get_by_role("heading", name="课程").wait_for(timeout=1500)
        self.page.evaluate("location.hash = '#/course/zhs/shared-1/qa'")
        self.page.get_by_text("问答互动", exact=True).wait_for(timeout=1500)
        self.server.release_score.set()
        self.page.wait_for_timeout(900)
        self.assertEqual(self.server.score_requests, 2)


if __name__ == "__main__":
    unittest.main()
