import http.client
import json
import tempfile
import threading
import time
import unittest
import unittest.mock
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from unittest.mock import Mock, patch

from core.auth import PlatformUnavailable
from core.reporting import ProgressEvent
from core.settings import SettingsStore
from web.server import PLATFORMS, HttpError, LocalAccess, Studia, _course, make_handler


class WebServerTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.app = Studia(SettingsStore(directory.name), oauth=Mock(return_value=None))
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), None)
        self.port = self.server.server_address[1]
        self.server.RequestHandlerClass = make_handler(LocalAccess(self.app, self.port))
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def request(self, method, path, *, token=True, host=None, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        self.addCleanup(conn.close)
        headers = {"Host": host or "127.0.0.1:%d" % self.port}
        if token:
            headers["X-Studia-Token"] = self.app.token
        data = None
        if body is not None:
            data = json.dumps(body)
            headers["Content-Type"] = "application/json"
        conn.request(method, path, body=data, headers=headers)
        response = conn.getresponse()
        return response.status, response.read()

    def test_api_requires_token_and_own_host(self):
        self.assertEqual(self.request("GET", "/api/state", token=False)[0], 403)
        self.assertEqual(self.request("GET", "/api/state", host="evil.example")[0], 403)
        self.assertEqual(self.request("GET", "/", host="evil.example")[0], 403)
        status, body = self.request("GET", "/api/state")
        self.assertEqual(status, 200)
        state = json.loads(body)
        self.assertEqual([p["id"] for p in state["platforms"]], ["mooc", "zhs"])
        self.assertFalse(any(p["logged_in"] for p in state["platforms"]))
        self.assertEqual(state["jobs"], [])

    def test_event_stream_asks_proxies_not_to_buffer(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        self.addCleanup(conn.close)
        conn.request("GET", "/api/events?t=" + self.app.token, headers={"Host": "127.0.0.1:%d" % self.port})
        self.assertEqual(conn.getresponse().getheader("X-Accel-Buffering"), "no")

    def test_static_files_stay_inside_the_bundle(self):
        self.assertEqual(self.request("GET", "/")[0], 200)
        self.assertEqual(self.request("GET", "/../settings.py")[0], 404)
        self.assertEqual(self.request("GET", "/%2e%2e/settings.py")[0], 404)
        self.assertEqual(self.request("GET", "/mock.js")[0], 404)

    def test_one_connection_serves_many_requests_and_static_files_revalidate(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        self.addCleanup(conn.close)
        conn.request("GET", "/studia.js")
        response = conn.getresponse()
        response.read()
        etag, sock = response.getheader("ETag"), conn.sock
        self.assertEqual(response.getheader("Cache-Control"), "no-cache")
        conn.request("GET", "/studia.js", headers={"If-None-Match": etag})
        response = conn.getresponse()
        response.read()
        self.assertEqual(response.status, 304)
        conn.request("GET", "/api/state", headers={"X-Studia-Token": self.app.token})
        response = conn.getresponse()
        self.assertEqual((response.status, response.getheader("Cache-Control")), (200, "no-store"))
        response.read()
        self.assertIs(conn.sock, sock)

    def test_page_names_its_build_so_an_open_page_notices_an_update(self):
        build = json.loads(self.request("GET", "/api/state")[1])["build"]
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        self.addCleanup(conn.close)
        conn.request("GET", "/")
        response = conn.getresponse()
        page = response.read().decode()
        self.assertIn('src="studia.js?v=%s"' % build, page)
        self.assertIn('href="studia.css?v=%s"' % build, page)
        self.assertEqual(response.getheader("ETag"), '"%s"' % build)
        self.assertEqual(self.request("GET", "/studia.js?v=" + build)[0], 200)
        with patch("web.server.static_build", return_value="newer"):  # a file it loads changed: no 304 for the old page
            conn.request("GET", "/", headers={"If-None-Match": '"%s"' % build})
            self.assertIn('src="studia.js?v=newer"', conn.getresponse().read().decode())

    def test_static_files_are_gzipped_for_browsers_that_ask(self):
        import gzip
        from web.server import STATIC
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        self.addCleanup(conn.close)
        conn.request("GET", "/studia.js", headers={"Accept-Encoding": "gzip, deflate, br"})
        response = conn.getresponse()
        packed = response.read()
        self.assertEqual(response.getheader("Content-Encoding"), "gzip")
        self.assertEqual(response.getheader("Vary"), "Accept-Encoding")
        self.assertEqual(gzip.decompress(packed), (STATIC / "studia.js").read_bytes())
        self.assertLess(len(packed), len(gzip.decompress(packed)) // 2)
        etag = response.getheader("ETag")
        self.assertTrue(etag.endswith('-gz"'))
        conn.request("GET", "/studia.js", headers={"Accept-Encoding": "gzip", "If-None-Match": etag})
        response = conn.getresponse()
        response.read()
        self.assertEqual(response.status, 304)
        conn.request("GET", "/studia.js")  # no gzip asked: the plain file, under its own tag
        response = conn.getresponse()
        self.assertEqual((response.getheader("Content-Encoding"), response.read()), (None, (STATIC / "studia.js").read_bytes()))
        self.assertNotEqual(response.getheader("ETag"), etag)

    def test_versioned_assets_are_cached_for_good_and_stale_ones_revalidate(self):
        build = json.loads(self.request("GET", "/api/state")[1])["build"]
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        self.addCleanup(conn.close)
        conn.request("GET", "/")
        self.assertIn('src="theme.js?v=%s"' % build, conn.getresponse().read().decode())
        for name in ("studia.js", "studia.css", "theme.js"):
            conn.request("GET", "/%s?v=%s" % (name, build))
            response = conn.getresponse()
            response.read()
            self.assertEqual(response.getheader("Cache-Control"), "public, max-age=31536000, immutable", name)
        conn.request("GET", "/studia.js?v=000000000000")
        response = conn.getresponse()
        response.read()
        self.assertEqual(response.getheader("Cache-Control"), "no-cache")
        conn.request("GET", "/")
        response = conn.getresponse()
        response.read()
        self.assertEqual(response.getheader("Cache-Control"), "no-cache")  # the page itself always revalidates

    def test_server_header_does_not_name_the_python_version(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        self.addCleanup(conn.close)
        conn.request("GET", "/")
        response = conn.getresponse()
        response.read()
        self.assertEqual(response.getheader("Server"), "Studia")

    def test_answer_pace_is_the_persons_own_choice_locally(self):
        self.assertEqual(json.loads(self.request("GET", "/api/settings")[1])["pace_locked"], False)
        self.assertEqual(self.request("POST", "/api/settings/pace", body={"pace": "fast"})[0], 200)
        self.assertEqual(self.app.answer_pace(), "fast")

    def test_courses_need_login_and_jobs_validate_input(self):
        self.assertEqual(self.request("GET", "/api/platforms/zhs/courses")[0], 401)
        self.assertEqual(self.request("GET", "/api/platforms/nope/courses")[0], 404)
        self.assertEqual(self.request("POST", "/api/jobs", body={"platform": "zhs", "type": "rm", "course": "x"})[0], 400)
        self.assertEqual(self.request("POST", "/api/jobs", body={"platform": "mooc", "type": "review", "course": "x"})[0], 400)
        self.assertEqual(self.request("GET", "/api/platforms/mooc/tasks?course=x")[0], 401)

    def test_jobs_run_in_parallel_except_on_the_same_course_or_zhs_video(self):
        self.app.platforms["zhs"].rows = [{"courseName": "课", "zhs": {"kind": "shared", "courseId": 1}}]
        running = {"id": "a1", "kind": "study", "title": "自动学习", "platform": "zhs", "course": "shared-1",
                   "course_name": "网络课", "started": 0, "cancel": threading.Event()}
        self.app.jobs = {"a1": running}
        status, body = self.request("POST", "/api/jobs", body={"platform": "zhs", "type": "review", "course": "shared-1"})
        self.assertEqual(status, 409)
        self.assertIn("正在自动学习", json.loads(body)["error"])
        check = self.app._check_conflicts
        with self.assertRaisesRegex(Exception, "只能播放一个视频"):
            check("zhs", "shared-2", "study")
        check("zhs", "shared-1", "answer")       # answering the same course is fine
        self.app.zhs_parallel = lambda: True     # the admin switch: other courses may study too
        check("zhs", "shared-2", "study")
        with self.assertRaisesRegex(Exception, "正在自动学习"):
            check("zhs", "shared-1", "review")   # but never two in the same course
        self.app.zhs_parallel = lambda: False
        check("mooc", "m1", "study")             # other platforms are independent
        self.app.jobs = {"a1": dict(running, platform="mooc", course="m1")}
        check("mooc", "m2", "study")             # MOOC courses study side by side
        with self.assertRaisesRegex(Exception, "正在自动学习"):
            check("mooc", "m1", "study")
        self.app.jobs = {str(i): dict(running, id=str(i), platform="mooc", course=str(i)) for i in range(20)}
        with self.assertRaisesRegex(Exception, "排队的任务已有"):
            check("mooc", "m99", "answer")

    def test_finished_job_lands_in_history_with_its_lines(self):
        platform = self.app.platforms["zhs"]
        platform.rows = [{"courseName": "网络课", "zhs": {"kind": "ai", "courseId": "c1"}}]
        platform.client = Mock()
        platform.spec = dict(platform.spec, handler=lambda **kwargs: kwargs["on_progress"](
            ProgressEvent("result", "第一节", status="success")))
        status, body = self.request("POST", "/api/jobs", body={"platform": "zhs", "type": "study", "course": "ai-c1"})
        self.assertEqual(status, 200)
        # The page shows the job from the reply when a proxy holds the event stream back.
        started = json.loads(body)["job"]
        self.assertEqual((started["id"], started["course"]), (json.loads(body)["id"], "ai-c1"))
        for _ in range(50):
            if not self.app.jobs:
                break
            time.sleep(0.02)
        history = json.loads(self.request("GET", "/api/jobs")[1])["history"]
        self.assertEqual(history[0]["state"], "done")
        self.assertEqual((history[0]["platform"], history[0]["course_name"]), ("zhs", "网络课"))
        self.assertEqual(history[0]["lines"][0]["text"], "第一节 · 完成")

    def test_live_cookies_are_saved_back_and_logout_stays_out(self):
        platform = self.app.platforms["zhs"]
        self.app.store.save_session("zhs", Mock(access_token="from-sign-in"))
        platform.client = Mock(access_token="renewed-while-running")
        self.app.shutdown()
        self.assertEqual(self.app.store.session("zhs")["access_token"], "renewed-while-running")
        self.app.logout("zhs")
        self.app.save_sessions()
        self.assertIsNone(self.app.store.session("zhs"))

    def test_job_progress_survives_a_page_opened_mid_run(self):
        job = {"id": "j1", "lines": [], "progress": {}}
        self.app.jobs["j1"] = job
        report = self.app.progress_of(job)
        report(ProgressEvent("begin", "智慧树学习", 2, unit="门课程"))
        report(ProgressEvent("unit", "第二节", status="running", key="u2"))
        report(ProgressEvent("result", "网络课", status="success"))
        report(ProgressEvent("resources", "网络课", 616, unit="项资源", completed=165))
        self.assertEqual(job["progress"], {
            "overall": {"name": "智慧树学习", "total": 2, "done": 1, "unit": "门课程"},
            "unit": {"name": "第二节", "key": "u2"},
            "sub": {"name": "网络课", "done": 165, "total": 616, "unit": "项"}})

    def test_captcha_leaves_the_job_waiting_for_the_user(self):
        from zhs.api import CaptchaRequired
        platform = self.app.platforms["zhs"]
        platform.rows = [{"courseName": "网络课", "zhs": {"kind": "ai", "courseId": "c1"}}]
        platform.client = Mock()
        platform.spec = dict(platform.spec, handler=lambda **kwargs: Mock(blocked=CaptchaRequired("请先完成滑块验证")),
                             units=lambda client, row: [{"name": "第一章", "units": []}])
        status, body = self.request("GET", "/api/platforms/zhs/units?course=ai-c1")
        self.assertEqual((status, json.loads(body)["chapters"][0]["name"]), (200, "第一章"))
        self.assertEqual(self.request("POST", "/api/jobs", body={"platform": "zhs", "type": "study", "course": "ai-c1"})[0], 200)
        for _ in range(50):
            if not self.app.jobs:
                break
            time.sleep(0.02)
        job = json.loads(self.request("GET", "/api/jobs")[1])["history"][0]
        self.assertEqual((job["state"], job["summary"]), ("waiting", "请先完成滑块验证"))

    def test_model_test_records_health_and_default_model_cannot_be_deleted(self):
        from ai.client import AIConfig
        store = self.app.store
        store.ensure_default_model(AIConfig("https://mochif.com/v1", "gemini-3.8-flash", "test-shared-key"))
        profile_id = store.save_ai_profile(AIConfig("https://api.example.com/v1", "m", "sk-secret-value-1234"))
        with unittest.mock.patch("web.server.AIClient") as client:
            client.return_value.check_connection.side_effect = __import__("ai.client", fromlist=["AIError"]).AIError("401")
            status, body = self.request("POST", "/api/settings/models/%s/test" % profile_id)
        self.assertEqual((status, json.loads(body)["health"]), (200, "error"))
        models = {m["id"]: m for m in json.loads(self.request("GET", "/api/settings")[1])["models"]}
        self.assertEqual(models[profile_id]["health"], "error")
        default = next(m for m in models.values() if not m["deletable"])
        self.assertEqual(self.request("POST", "/api/settings/models/%s/delete" % default["id"])[0], 400)
        self.assertEqual(self.request("POST", "/api/settings/models/%s/delete" % profile_id)[0], 200)

    def test_mooc_tasks_are_listed_by_type_with_scores(self):
        platform = self.app.platforms["mooc"]
        row = {"courseName": "英语", "courseId": "c1"}
        platform.rows, platform.client = [row], Mock()
        entries = [(row, {"id": "e/1", "name": "第一单元作业", "score": 92, "_completion_status": "submitted"}, 1),
                   (row, {"id": "q2", "title": "随堂测验", "score": None, "_completion_status": "not_started"}, 3)]
        with unittest.mock.patch("web.server._mooc_catalog", return_value=entries):
            status, body = self.request("GET", "/api/platforms/mooc/tasks?course=c1")
        tasks = json.loads(body)["tasks"]
        self.assertEqual(status, 200)
        self.assertEqual([(t["id"], t["category"], t["score"]) for t in tasks], [("1-e_1", "作业", "92"), ("3-q2", "测验", None)])
        self.assertEqual(tasks[0]["status"], "已提交")
        self.assertIn("1-e_1", platform.entries["c1"])

    def test_each_handed_in_paper_drops_the_paper_list_before_the_page_hears_of_it(self):
        # The page rereads the papers on a "submitted" result; a list cached before it would still say 0 points.
        platform = self.app.platforms["mooc"]
        row = {"courseName": "英语", "courseId": "c1"}
        platform.rows, platform.client = [row], Mock()
        self.app._ai, self.app.mooc_memory = Mock(), Mock()
        cached = []

        def run_paper(course, item, category):
            platform.cache[("tasks", "c1")] = (time.time(), ({}, [{"id": item["id"], "score": "0"}]))
            return {"status": "submitted"}

        def publish(event):
            if event.get("kind") == "result":
                cached.append(("tasks", "c1") in platform.cache)

        job = {"id": "j1", "course": "c1", "cancel": threading.Event()}
        selected = [(row, {"id": "e1", "name": "第一单元作业"}, 1), (row, {"id": "e2", "name": "第二单元作业"}, 1)]
        with patch("web.server.AnswerRunner") as runner, patch("web.server.ExamAPI"), \
                patch.object(self.app, "publish", side_effect=publish):
            runner.return_value.run_paper.side_effect = run_paper
            self.assertEqual(self.app._answer(platform, selected, True, job), "处理完成 2/2 份试卷")
        self.assertEqual(cached, [False, False])

    def test_a_list_with_an_exam_to_open_on_the_platform_is_kept_only_briefly(self):
        # 智慧树's exams open on the platform: coming back after opening one must not find the old list for 10 min.
        platform = self.app.platforms["mooc"]
        row = {"courseName": "英语", "courseId": "c1"}
        platform.rows, platform.client = [row], Mock()
        waiting = {"id": "e1", "name": "期末考试", "_completion_status": "not_started",
                   "_unavailable": ("未开考", "先在平台网页上开考，回到这里会自动刷新。"), "_waiting": True}
        reads = []

        def catalog(client, course):
            reads.append(1)
            return [(row, dict(waiting) if len(reads) == 1 else {"id": "e1", "name": "期末考试"}, 2)]

        with unittest.mock.patch("web.server._mooc_catalog", side_effect=catalog):
            first = json.loads(self.request("GET", "/api/platforms/mooc/tasks?course=c1")[1])["tasks"][0]
            self.assertEqual((first["available"], first["waiting"]), (False, True))
            self.request("GET", "/api/platforms/mooc/tasks?course=c1")
            self.assertEqual(len(reads), 1)  # within the short wait the list is still reused
            stamp, value = platform.cache[("tasks", "c1")]
            platform.cache[("tasks", "c1")] = (stamp - 31, value)
            again = json.loads(self.request("GET", "/api/platforms/mooc/tasks?course=c1")[1])["tasks"][0]
        self.assertEqual(len(reads), 2)
        self.assertEqual((again["available"], again["waiting"]), (True, False))

    def _exam_with_captcha(self):
        platform = self.app.platforms["zhs"]
        row = {"courseName": "导论", "zhs": {"kind": "shared", "courseId": 3, "recruitId": 9}}
        exam = {"id": "sex-5XxWlDWz-wM3vWWJ5", "name": "期末考试", "_captcha": True, "_start": True,
                "_entry": {"start": True, "remain": 1, "parentId": None, "reviewType": 0},
                "zhs": {"kind": "shared_exam", "recruitId": 9, "courseId": 3, "stuExamId": "5XxWlDWz", "examId": "wM3vWWJ5"}}
        homework = {"id": "shw-1-2", "name": "作业", "zhs": {"kind": "shared_homework", "stuExamId": 1, "examId": 2}}
        platform.rows, platform.client = [row], Mock()
        platform.entries["shared-3"] = {"2-sex-5XxWlDWz-wM3vWWJ5": (row, exam, 2), "1-shw-1-2": (row, homework, 1)}
        platform.client.shared_exam_captcha.side_effect = [(b"\x89PNG-1", "k1"), (b"GIF89a-2", "k2"), (b"\x89PNG-3", "k3")]
        return platform

    def test_an_exam_picture_code_is_read_and_checked_with_the_accounts_login(self):
        platform = self._exam_with_captcha()
        checks = patch("web.server.exam_entry_check", return_value=("", "")).start()
        self.addCleanup(patch.stopall)
        status, body = self.request("GET", "/api/platforms/zhs/exam-captcha?course=shared-3&task=2-sex-5XxWlDWz-wM3vWWJ5")
        self.assertEqual(status, 200)
        got = json.loads(body)
        self.assertTrue(got["image"].startswith("data:image/png;base64,"))
        self.assertEqual((got["start"], got["remain"], got["warning"]), (True, 1, ""))
        self.assertEqual(platform.captcha, {"2-sex-5XxWlDWz-wM3vWWJ5": "k1"})
        self.assertEqual(checks.call_count, 1)

        platform.client.shared_exam_captcha_check.return_value = False
        status, body = self.request("POST", "/api/platforms/zhs/exam-captcha",
                                    body={"course": "shared-3", "task": "2-sex-5XxWlDWz-wM3vWWJ5", "code": "ab12"})
        wrong = json.loads(body)
        self.assertEqual((status, wrong["ok"]), (200, False))
        self.assertTrue(wrong["image"].startswith("data:image/gif;base64,"))  # a new picture to try
        platform.client.shared_exam_captcha_check.assert_called_with("ab12", "k1", "5XxWlDWz")

        platform.client.shared_exam_captcha_check.return_value = True
        status, body = self.request("POST", "/api/platforms/zhs/exam-captcha",
                                    body={"course": "shared-3", "task": "2-sex-5XxWlDWz-wM3vWWJ5", "code": " cd34 "})
        self.assertEqual((status, json.loads(body)), (200, {"ok": True}))
        platform.client.shared_exam_captcha_check.assert_called_with("cd34", "k2", "5XxWlDWz")
        self.assertEqual(platform.captcha, {})
        self.assertEqual(checks.call_count, 1)  # the new picture after the wrong code did not walk them again
        self.assertEqual(platform.entry_checked, {})  # the next entry does

        # Each picture is good for one try: sending again without a new one asks for one.
        status, _ = self.request("POST", "/api/platforms/zhs/exam-captcha",
                                 body={"course": "shared-3", "task": "2-sex-5XxWlDWz-wM3vWWJ5", "code": "cd34"})
        self.assertEqual(status, 409)

    def test_an_exam_the_platform_page_must_enter_says_why_instead_of_a_code(self):
        platform = self._exam_with_captcha()
        with patch("web.server.exam_entry_check", return_value=("学校开了人脸识别，只能到平台网页开考。", "")):
            status, body = self.request("GET", "/api/platforms/zhs/exam-captcha?course=shared-3&task=2-sex-5XxWlDWz-wM3vWWJ5")
        self.assertEqual(status, 409)
        self.assertIn("人脸识别", json.loads(body)["error"])
        platform.client.shared_exam_captcha.assert_not_called()
        self.assertEqual((platform.captcha, platform.entry_checked), ({}, {}))
        with patch("web.server.exam_entry_check", return_value=("", "智慧树检测到这场考试有异常行为")):
            got = json.loads(self.request("GET", "/api/platforms/zhs/exam-captcha?course=shared-3&task=2-sex-5XxWlDWz-wM3vWWJ5")[1])
        self.assertIn("异常行为", got["warning"])

    def test_only_exams_entered_with_a_picture_code_have_one(self):
        self._exam_with_captcha()
        self.assertEqual(self.request("GET", "/api/platforms/zhs/exam-captcha?course=shared-3&task=1-shw-1-2")[0], 404)
        self.assertEqual(self.request("GET", "/api/platforms/zhs/exam-captcha?course=shared-3&task=nope")[0], 404)

    def test_fresh_reads_the_paper_list_past_the_cache(self):
        platform = self.app.platforms["mooc"]
        row = {"courseName": "英语", "courseId": "c1"}
        platform.rows, platform.client = [row], Mock()
        reads = []

        def catalog(client, course):
            reads.append(1)
            return [(row, {"id": "e%d" % len(reads), "name": "作业"}, 1)]

        with unittest.mock.patch("web.server._mooc_catalog", side_effect=catalog):
            self.request("GET", "/api/platforms/mooc/tasks?course=c1")
            self.request("GET", "/api/platforms/mooc/tasks?course=c1")
            self.assertEqual(len(reads), 1)
            self.request("GET", "/api/platforms/mooc/tasks?course=c1&fresh=1")
        self.assertEqual(len(reads), 2)

    def test_a_list_read_under_way_when_a_paper_is_handed_in_is_not_kept(self):
        platform = self.app.platforms["mooc"]
        entered, release = threading.Event(), threading.Event()

        def before_the_paper():
            entered.set()
            self.assertTrue(release.wait(3))
            return "0 分"

        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(self.app._cached, platform, ("tasks", "c1"), False, before_the_paper)
            self.assertTrue(entered.wait(2))
            self.app._forget(platform, "c1")
            release.set()
            self.assertEqual(pending.result(), "0 分")
        self.assertNotIn(("tasks", "c1"), platform.cache)
        self.assertEqual(self.app._cached(platform, ("tasks", "c1"), False, lambda: "92 分"), "92 分")
        self.assertEqual(platform.cache[("tasks", "c1")][1], "92 分")

    def test_settings_never_return_full_api_key(self):
        from ai.client import AIConfig
        store = self.app.store
        store.activate_ai_profile(store.save_ai_profile(
            AIConfig("https://api.example.com/v1", "m", "sk-secret-value-1234")))
        status, body = self.request("GET", "/api/settings")
        self.assertEqual(status, 200)
        self.assertNotIn("secret-value", body.decode())
        self.assertIn("sk-…1234", body.decode())

    def test_course_mapping(self):
        row = {"courseName": "导论", "courseInfoName": "共享课", "studySpeed": "99.6",
               "zhs": {"kind": "shared", "courseId": 7}}
        self.assertEqual(_course("zhs", row), {"id": "shared-7", "platform": "zhs", "name": "导论", "type": "共享课",
                                               "kind": "shared", "progress": 100,
                                               "features": {"answer": True, "review": True, "qa": True}, "shares": None})
        self.assertEqual(_course("mooc", {"courseName": "高数", "courseId": "a/b"})["id"], "a_b")
        self.assertIsNone(_course("zhs", {"zhs": {"kind": "ai", "courseId": 8}})["progress"])

    def test_qr_login_completion_saves_session(self):
        client = Mock()
        client.login_qr_status.return_value = {"status": 1, "oncePassword": "once"}
        sso = threading.Event()
        client.shared_exam_sso.side_effect = lambda: sso.wait(5)
        self.app.platforms["zhs"].qr = {"a": {"client": client, "qr": "q", "refreshes": 0}}
        self.app.store.save_session = Mock()
        # The page is told while the exam sign-on still runs: its redirects kept people watching the code.
        self.assertEqual(self.app.login_status("zhs", "a")["status"], "done")
        client.finish_qr_login.assert_called_once_with("once")
        self.app.store.save_session.assert_called_once_with("zhs", client)
        self.assertIs(self.app.platforms["zhs"].client, client)
        sso.set()
        for _ in range(500):  # then the cookies are saved again, so a restart still finds the exam session
            if self.app.store.save_session.call_count == 2:
                break
            time.sleep(0.01)
        self.assertEqual(self.app.store.save_session.call_count, 2)

    def test_each_page_keeps_its_own_qr_code(self):
        codes = iter(range(10))
        from web.server import PLATFORMS
        original = PLATFORMS["zhs"]["api"]
        PLATFORMS["zhs"]["api"] = lambda: Mock(
            login_qr=Mock(return_value=("q%d" % next(codes), b"png")),
            login_qr_status=Mock(return_value={"status": -1}))
        self.addCleanup(lambda: PLATFORMS["zhs"].__setitem__("api", original))
        first = self.app.login_start("zhs")["id"]
        second = self.app.login_start("zhs")["id"]  # a second tab opens the login page
        platform = self.app.platforms["zhs"]
        platform.qr[first]["client"].login_qr_status.return_value = {"status": 1, "oncePassword": "o"}
        self.app.store.save_session = Mock()
        # Scanning the code the first tab shows still signs in, though the second tab asked later.
        self.assertEqual(self.app.login_status("zhs", first)["status"], "done")
        self.assertEqual(self.app.login_status("zhs", second)["status"], "failed")
        self.assertEqual(platform.qr, {})

    def test_a_failed_qr_handover_is_reported_not_left_spinning(self):
        client = Mock()
        client.login_qr_status.return_value = {"status": 1, "oncePassword": "once"}
        client.finish_qr_login.side_effect = PlatformUnavailable("暂时无法连接智慧树")
        self.app.platforms["zhs"].qr = {"a": {"client": client, "qr": "q", "refreshes": 0}}
        result = self.app.login_status("zhs", "a")
        self.assertEqual(result["status"], "failed")
        self.assertIn("暂时无法连接智慧树", result["message"])
        self.assertIsNone(self.app.platforms["zhs"].client)

    def test_sign_in_events_reach_the_log_file(self):
        import logging
        from web import server
        self.assertTrue(any(isinstance(h, logging.FileHandler) for h in server.logger.handlers))

    def test_browser_login_runs_in_background_and_reports_failure(self):
        self.assertEqual(self.app.login_start("mooc")["status"], "waiting")
        for _ in range(50):
            if self.app.platforms["mooc"].login["status"] != "waiting":
                break
            time.sleep(0.02)
        result = self.app.login_status("mooc")
        self.assertEqual(result["status"], "failed")
        self.assertIsNone(self.app.platforms["mooc"].login)

    def test_a_login_result_nobody_read_is_not_reported_after_signing_out(self):
        # A phone back from the SSO page lands signed in and goes home without reading the result. Opening the
        # login page after a logout (or an expired login) must not announce that old login as a new one.
        client = Mock(access_token="cookies")
        client.my_course_list.return_value = {"rows": []}
        app = Studia(self.app.store, oauth_url=lambda pid, here=False: "https://sso.example/")
        with patch.dict(PLATFORMS["mooc"], {"api": lambda **kw: client}):
            app.login_start("mooc")
            app.finish_browser_login("mooc", "token")
        app.logout("mooc")
        with self.assertRaises(HttpError) as caught:
            app.login_status("mooc")
        self.assertEqual(caught.exception.status, 409)


if __name__ == "__main__":
    unittest.main()
