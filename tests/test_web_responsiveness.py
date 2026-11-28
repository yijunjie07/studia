"""Exercise the real browser UI with slow and failing platform responses."""
import json
import queue
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
            if self.server.events is None:
                self.send_response(204)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                while True:
                    event = self.server.events.get(timeout=5)
                    if event is None:
                        break
                    self.wfile.write(("data: %s\n\n" % json.dumps(event)).encode())
                    self.wfile.flush()
            except (queue.Empty, BrokenPipeError, ConnectionResetError, OSError):
                pass
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
            data = {"/api/mode": {"mode": "hosted" if self.server.admin else "local"},
                    "/api/auth/me": {"user": {"id": "a1", "username": "admin", "role": "admin"}, "csrf": "c", "mail": False},
                    "/api/settings": {"models": [], "concurrency": {"ai": 1, "study": 1}},
                    "/api/state": {"platforms": PLATFORMS, "jobs": self.server.own_jobs, "history": [],
                                   **({"site_jobs": self.server.site_jobs} if self.server.admin else {})},
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
        self.server.admin = False
        self.server.own_jobs = []
        self.server.site_jobs = 0
        self.server.events = None
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
        self.page = self.browser.new_page()
        self.base = "http://127.0.0.1:%d/?t=test" % self.server.server_port

    def tearDown(self):
        self.server.release_courses.set()
        self.server.release_score.set()
        if self.server.events is not None:
            self.server.events.put(None)
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
        self.page.get_by_role("heading", name="已发布").wait_for(timeout=3000)
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
        self.page.get_by_role("heading", name="已发布").wait_for(timeout=3000)
        self.assertTrue(self.server.score_requested.wait(3))
        self.page.evaluate("location.hash = '#/home'")
        self.page.get_by_role("heading", name="课程").wait_for(timeout=1500)
        self.page.evaluate("location.hash = '#/course/zhs/shared-1/qa'")
        self.page.get_by_role("heading", name="已发布").wait_for(timeout=1500)
        self.server.release_score.set()
        self.page.wait_for_timeout(900)
        self.assertEqual(self.server.score_requests, 2)

    def test_admin_nav_shows_site_wide_job_count_and_updates_from_events(self):
        self.server.release_courses.set()
        self.server.admin = True
        self.server.site_jobs = 2
        self.server.own_jobs = [{"id": "j1", "kind": "study", "title": "自动学习", "course": "shared-1",
                                 "course_name": "课程", "platform": "zhs", "state": "running", "summary": "",
                                 "started": 1, "ended": None, "lines": []}]
        self.server.events = queue.Queue()
        self.page.goto("http://127.0.0.1:%d/#/home" % self.server.server_port, wait_until="domcontentloaded")
        nav_jobs = self.page.locator('.nav .nav_item[data-go="#/jobs"]')
        mobile_badge = self.page.locator('.mtabs .mtab[data-go="#/jobs"] .badge')
        nav_jobs.locator(".live", has_text="3 个进行中").wait_for(timeout=3000)
        self.assertEqual(mobile_badge.text_content(), "3")

        self.server.site_jobs = 4
        self.server.events.put({"type": "site_jobs", "count": 4})
        nav_jobs.locator(".live", has_text="5 个进行中").wait_for(timeout=3000)
        self.assertEqual(mobile_badge.text_content(), "5")

        nav_jobs.click()
        self.page.locator('.tab[data-go="#/jobs/all"] .n', has_text="4").wait_for(timeout=3000)
        self.page.locator('.tab[data-go="#/jobs"] .n', has_text="1").wait_for(timeout=3000)

        self.server.own_jobs = []
        self.server.site_jobs = 0
        self.server.events.put({"type": "job", "id": "j1", "kind": "study", "title": "自动学习",
                                "course": "shared-1", "course_name": "课程", "platform": "zhs",
                                "state": "done", "summary": "完成", "started": 1, "ended": 2})
        self.server.events.put({"type": "site_jobs", "count": 0})
        self.page.wait_for_function('() => !document.querySelector(\'.nav .nav_item[data-go="#/jobs"] .live\')', timeout=3000)
        self.assertEqual(mobile_badge.count(), 0)

    def test_qa_clock_renders_dial_and_ticks_live(self):
        self.page.goto("http://127.0.0.1:%d/?mock#/course/zhs/shared-1/qa" % self.server.server_port,
                       wait_until="domcontentloaded")
        clock = self.page.locator('.qa_clock[data-qa-clock="zhs"]')
        clock.wait_for(timeout=3000)
        self.assertEqual(clock.locator("svg.qa_dial").count(), 1)
        first = clock.locator("[data-qa-clock-num]").text_content()
        self.assertRegex(first, r"^\d{2}:\d{2}:\d{2}$")
        self.page.wait_for_function(
            "(prev) => document.querySelector('[data-qa-clock-num]')?.textContent !== prev",
            arg=first, timeout=3000,
        )

        self.page.goto("http://127.0.0.1:%d/?mock&rescan#/course/zhs/shared-1/qa" % self.server.server_port,
                       wait_until="domcontentloaded")
        lapsed = self.page.locator('.qa_clock.lapsed[data-qa-clock="zhs"]')
        lapsed.wait_for(timeout=3000)
        self.assertEqual(lapsed.locator("[data-qa-clock-num]").text_content(), "00:00:00")

    def test_course_hero_and_qa_do_not_overflow_on_360px_phone(self):
        self.page.set_viewport_size({"width": 360, "height": 780})
        self.page.goto("http://127.0.0.1:%d/?mock#/course/zhs/shared-1/qa" % self.server.server_port,
                       wait_until="domcontentloaded")
        self.page.locator(".qa_clock").wait_for(timeout=3000)
        overflow = self.page.evaluate("""() => {
            const hero = document.querySelector('.hero');
            const hr = hero.getBoundingClientRect();
            const out = [...hero.querySelectorAll('.hero_stat')].filter((el) => el.getBoundingClientRect().right > hr.right + 1).length;
            return { scrollW: document.documentElement.scrollWidth, innerW: window.innerWidth, heroOut: out };
        }""")
        self.assertLessEqual(overflow["scrollW"], overflow["innerW"])
        self.assertEqual(overflow["heroOut"], 0)

    def test_profile_tab_oauth_admin_and_passwordless_linuxdo_ui(self):
        import os
        import tempfile
        from unittest.mock import patch
        import web.accounts
        from web.hosting import COOKIE, HostedAccess, Hub
        from web.server import make_handler

        errors = []
        self.page.on("pageerror", lambda err: errors.append(str(err)))
        with tempfile.TemporaryDirectory() as directory, patch.object(web.accounts, "ITERATIONS", 1000):
            srv = ThreadingHTTPServer(("127.0.0.1", 0), None)
            port = srv.server_address[1]
            hub = Hub(directory, "http://127.0.0.1:%d" % port, key=os.urandom(32))
            hub.accounts.create_user("admin", "admin-password", role="admin")
            hub.site_store.set("smtp", {"host": "smtp.example.com", "port": 465, "security": "ssl",
                                        "username": "a@example.com", "password": "pw",
                                        "sender": "a@example.com", "sender_name": "Studia"})
            srv.RequestHandlerClass = make_handler(HostedAccess(hub, port))
            threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
            base = "http://127.0.0.1:%d" % port
            try:
                # 1. Login page hides Linux DO entry while OAuth master switch is off.
                self.page.goto(base + "/", wait_until="domcontentloaded")
                self.page.get_by_role("heading", name="登录").wait_for(timeout=3000)
                self.assertEqual(self.page.locator(".auth_oauth").count(), 0)

                # 2. Sign in as admin (password account without email sees email-prompt), dismiss it, then configure OAuth.
                self.page.locator('input[name="username"]').fill("admin")
                self.page.locator('input[name="password"]').fill("admin-password")
                self.page.locator(".auth_submit").click()
                self.page.wait_for_function("() => !document.body.classList.contains('signed-out')", timeout=3000)
                self.page.locator('dialog[aria-labelledby="email-prompt"] [data-later]').click()
                self.page.wait_for_function("() => !document.querySelector('dialog[open]')", timeout=3000)
                self.page.goto(base + "/#/admin/oauth", wait_until="domcontentloaded")
                self.page.get_by_role("heading", name="OAuth 总开关").wait_for(timeout=3000)
                self.assertTrue(self.page.locator('[data-oauth-enabled="1"]').is_disabled())
                self.assertIn(base + "/auth/linuxdo/callback", self.page.content())
                self.page.locator("[data-linuxdo-edit]").click()
                self.page.locator('dialog input[name="client_id"]').fill("demo-client-id")
                self.page.locator('dialog input[name="client_secret"]').fill("demo-secret-9999")
                self.page.locator("dialog button.primary").click()
                self.page.locator(".pill.blue", has_text="已配置").wait_for(timeout=3000)
                self.page.locator('[data-oauth-enabled="1"]').click()
                self.page.locator('[data-oauth-enabled="1"][aria-pressed="true"]').wait_for(timeout=3000)

                # 3. 个人资料 is a full profile page (hero + stats + 学习平台 + 账号与安全); 设置 only has AI 模型 & 偏好.
                self.page.locator("[data-me]").click()
                self.page.locator('.me_menu [data-go="#/profile"]').wait_for(timeout=3000)
                self.page.locator('.me_menu [data-go="#/settings"]').wait_for(timeout=3000)
                self.page.locator('.me_menu [data-go="#/profile"]').click()
                self.page.locator(".profile_hero").wait_for(timeout=3000)
                self.assertEqual(self.page.locator(".profile_stats .pstat").count(), 3)
                self.page.get_by_role("heading", name="学习平台").wait_for(timeout=3000)
                self.page.get_by_role("heading", name="账号与安全").wait_for(timeout=3000)
                self.page.locator("[data-linuxdo-bind]").wait_for(timeout=3000)
                self.assertGreater(self.page.get_by_text("邮箱", exact=True).count(), 0)
                self.assertGreater(self.page.get_by_text("密码", exact=True).count(), 0)

                self.page.goto(base + "/#/settings", wait_until="domcontentloaded")
                tabs = self.page.locator('.tabs [role="tab"]').all_text_contents()
                self.assertEqual(tabs, ["AI 模型", "偏好"])

                # 4. Sign out: login page now displays the Linux DO OAuth button.
                self.page.context.clear_cookies()
                self.page.goto(base + "/", wait_until="domcontentloaded")
                oauth_link = self.page.locator('a.auth_oauth[href="/auth/linuxdo/start"]')
                oauth_link.wait_for(timeout=3000)
                self.assertEqual(oauth_link.text_content().strip(), "使用 Linux DO 登录")

                # 5. Passwordless Linux DO user sees 个人资料 with Linux DO info, no email/password rows, and no email modal.
                uid, _ = hub.accounts.login_oauth("linuxdo", "777", username="ld_user", name="LD", trust_level=2)
                tok = hub.sessions.create(uid)
                self.page.context.add_cookies([{"name": COOKIE, "value": tok, "url": base}])
                self.page.goto("about:blank")
                self.page.goto(base + "/#/profile", wait_until="domcontentloaded")
                self.page.locator(".profile_hero").wait_for(timeout=3000)
                self.page.get_by_text("@ld_user · 2 级").first.wait_for(timeout=3000)
                self.page.get_by_text("主登录方式").wait_for(timeout=3000)
                self.page.wait_for_timeout(300)
                self.assertEqual(self.page.locator("dialog[open]").count(), 0)
                self.assertEqual(self.page.locator("[data-linuxdo-unbind]").count(), 0)
                self.assertEqual(self.page.locator('[data-account-edit="email"]').count(), 0)
                self.assertEqual(self.page.locator('[data-account-edit="password"]').count(), 0)
            finally:
                srv.shutdown()
                srv.server_close()
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
