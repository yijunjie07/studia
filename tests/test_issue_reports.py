import os
import tempfile
import threading
import unittest
from unittest.mock import Mock

from core.issue_check import build_issue_check, format_issue_markdown, make_finding, summarize_issue_gaps
from core.settings import SettingsError, SettingsStore
from mooc.main import AIMoocHandler
from web.accounts import AccountError, Accounts
from web.hosting import HostedAccess, Hub
from web.server import JOBS, HttpError, Studia
from zhs.api import CaptchaRequired
from zhs.main import ZHSHandler


class IssueCheckCoreTest(unittest.TestCase):
    def test_build_issue_check_returns_none_when_no_findings(self):
        job = {
            "id": "j1",
            "kind": "study",
            "title": "自动学习",
            "platform": "mooc",
            "course": "c1",
            "course_name": "大学英语",
            "state": "done",
            "summary": "学习完成",
            "lines": [],
        }
        self.assertIsNone(build_issue_check(job, findings=[]))

    def test_build_issue_check_redacts_secrets_and_computes_stable_fingerprint(self):
        job = {
            "id": "j1",
            "kind": "study",
            "title": "自动学习",
            "platform": "mooc",
            "course": "c1",
            "course_name": "人工智能导论",
            "state": "done",
            "summary": "学习完成",
            "lines": [
                {"text": "Bearer secret-jwt-token failed", "level": "error", "time": "10:01"},
                {"text": "正常日志", "level": "", "time": "10:00"},
            ],
        }
        f1 = make_finding(
            "unknown_type",
            name="互动实验",
            kind="h5_lab",
            detail="Authorization: Bearer top-secret-value 不支持",
            fields="id=u1, fileType=h5_lab, token=abc",
        )
        f2 = make_finding(
            "unverified_unit",
            name="互动实验",
            kind="h5_lab",
            detail="提交后平台未标记完成",
            fields="id=u1, fileType=h5_lab",
        )
        check_a = build_issue_check(
            job,
            findings=[f1, f2],
            course_meta={"type": "AI优课", "kind": "mooc", "progress": 75, "shares": None},
        )
        check_b = build_issue_check(
            dict(job, id="j2"),
            findings=[f2, f1],
            course_meta={"type": "AI优课", "kind": "mooc", "progress": 80, "shares": None},
        )
        self.assertIsNotNone(check_a)
        self.assertEqual(check_a["fingerprint"], check_b["fingerprint"])
        self.assertEqual(check_a["counts"]["unknown"], 1)
        self.assertEqual(check_a["counts"]["unverified"], 1)
        self.assertNotIn("top-secret-value", check_a["items"][0]["detail"])
        self.assertNotIn("secret-jwt-token", check_a["logs"][0]["text"])
        md = format_issue_markdown(check_a, note="第三章卡住了")
        self.assertIn("人工智能导论", md)
        self.assertIn("h5_lab", md)
        self.assertIn("第三章卡住了", md)
        self.assertNotIn("top-secret-value", md)

    def test_summarize_issue_gaps_aggregates_open_reports_across_courses(self):
        reports = [
            {
                "id": "r1",
                "platform": "mooc",
                "course_id": "m1",
                "course_name": "大学英语（二）",
                "status": "open",
                "source": "manual",
                "report_count": 3,
                "reporter_count": 2,
                "reporters": [{"username": "alice"}, {"username": "bob"}],
                "updated": 100.0,
                "payload": {
                    "items": [
                        {"code": "unknown_type", "bucket": "unknown", "label": "未适配资源类型", "kind": "vr_lab"},
                        {"code": "unknown_type", "bucket": "unknown", "label": "未适配资源类型", "kind": "vr_lab"},
                    ]
                },
            },
            {
                "id": "r2",
                "platform": "mooc",
                "course_id": "m2",
                "course_name": "智能制造导论",
                "status": "open",
                "source": "auto",
                "report_count": 2,
                "reporter_count": 2,
                "reporters": [{"username": "bob"}, {"username": "carol"}],
                "updated": 200.0,
                "payload": {
                    "items": [
                        {"code": "unknown_type", "bucket": "unknown", "label": "未适配资源类型", "kind": "vr_lab"},
                    ]
                },
            },
            {
                "id": "r3",
                "platform": "zhs",
                "course_id": "z1",
                "course_name": "人工智能智慧课",
                "status": "open",
                "source": "auto",
                "report_count": 4,
                "reporter_count": 1,
                "reporters": [{"username": "dave"}],
                "updated": 300.0,
                "payload": {
                    "items": [
                        {"code": "unverified_unit", "bucket": "unverified", "label": "提交后平台未标记完成", "kind": "9/7"},
                    ]
                },
            },
            {
                "id": "r4",
                "platform": "mooc",
                "course_id": "m3",
                "course_name": "已解决课程",
                "status": "resolved",
                "source": "manual",
                "report_count": 10,
                "reporter_count": 9,
                "reporters": [{"username": "eve"}],
                "updated": 400.0,
                "payload": {
                    "items": [
                        {"code": "unknown_type", "bucket": "unknown", "label": "未适配资源类型", "kind": "vr_lab"},
                    ]
                },
            },
        ]
        gaps = summarize_issue_gaps(reports)
        self.assertEqual([g["key"] for g in gaps], ["mooc|unknown_type|vr_lab", "zhs|unverified_unit|9/7"])
        top = gaps[0]
        self.assertEqual(top["course_count"], 2)
        self.assertEqual(top["report_count"], 2)
        self.assertEqual(top["user_count"], 3)
        self.assertEqual(top["hit_count"], 5)
        self.assertEqual(top["manual_count"], 1)
        self.assertEqual(top["auto_count"], 1)
        self.assertEqual(top["sample_course"], "智能制造导论")


class MoocStudyCheckTest(unittest.TestCase):
    def _client(self, cells, done_before, done_after=None, study_resp=None):
        client = Mock()
        client.study_design_list.return_value = [{"id": "ch1", "name": "第一章"}]
        done_calls = [list(done_before), list(done_before if done_after is None else done_after)]
        client.study_record_list.side_effect = lambda *a, **kw: done_calls.pop(0) if done_calls else list(done_before if done_after is None else done_after)
        client.get_cell_list.return_value = cells
        client.study_record.return_value = study_resp if study_resp is not None else {"code": 200, "msg": "ok"}
        client.clone.side_effect = lambda: client
        return client

    def test_mooc_records_unknown_skipped_and_unverified_but_ignores_normal_done_and_homework(self):
        cells = [
            {"id": "done1", "name": "已学视频", "fileType": "video", "courseId": "c1", "courseInfoId": "ci1"},
            {"id": "hw1", "name": "第一单元作业", "fileType": "作业", "courseId": "c1", "courseInfoId": "ci1"},
            {"id": "fold1", "name": "未展开文件夹", "fileType": "文件夹", "courseId": "c1", "courseInfoId": "ci1"},
            {"id": "h51", "name": "虚拟仿真实验", "fileType": "vr_lab", "courseId": "c1", "courseInfoId": "ci1"},
            {"id": "ok1", "name": "普通课件", "fileType": "ppt", "courseId": "c1", "courseInfoId": "ci1"},
        ]
        # After studying, ok1 is confirmed done, but h51 did NOT show up in study_record_list.
        client = self._client(cells, done_before=["done1"], done_after=["done1", "ok1"])
        course = {"id": "ci1", "courseId": "c1", "courseName": "智能制造导论", "studySpeed": 40}

        with unittest.mock.patch("mooc.main.time.sleep", return_value=None):
            handler = AIMoocHandler(client=client, course_rows=[course], max_workers=1)

        codes = {(f["code"], f["name"]) for f in handler.findings}
        self.assertIn(("skipped_unit", "未展开文件夹"), codes)
        self.assertIn(("unknown_type", "虚拟仿真实验"), codes)
        self.assertIn(("unverified_unit", "虚拟仿真实验"), codes)
        self.assertNotIn(("skipped_unit", "已学视频"), codes)
        self.assertNotIn(("skipped_unit", "第一单元作业"), codes)
        self.assertNotIn(("unverified_unit", "普通课件"), codes)

    def test_mooc_clean_course_produces_no_findings(self):
        cells = [
            {"id": "ok1", "name": "普通课件", "fileType": "ppt", "courseId": "c1", "courseInfoId": "ci1"},
            {"id": "hw1", "name": "单元测试", "fileType": "测验", "courseId": "c1", "courseInfoId": "ci1"},
        ]
        client = self._client(cells, done_before=[], done_after=["ok1"])
        course = {"id": "ci1", "courseId": "c1", "courseName": "干净课程", "studySpeed": 50}

        with unittest.mock.patch("mooc.main.time.sleep", return_value=None):
            handler = AIMoocHandler(client=client, course_rows=[course], max_workers=1)

        self.assertEqual(handler.findings, [])


class ZhsStudyCheckTest(unittest.TestCase):
    def test_zhs_ai_records_unverified_resource_when_study_status_stays_zero(self):
        client = Mock()
        client.ai_course_basic.return_value = {
            "cakeThemeList": [{"knowledgeList": [{"knowledgeId": 10, "knowledgeName": "知识点1"}]}]
        }
        # First call (during study) and second call (post-check): r2 stays studyStatus=0 despite ai_complete returning ok!
        r1 = {
            "studyStatus": 0,
            "resourcesDetail": {"resourcesUid": "u1", "resourcesName": "阅读文档", "resourcesType": 3, "resourcesDistributeType": 1},
        }
        r2 = {
            "studyStatus": 0,
            "resourcesDetail": {"resourcesUid": "u2", "resourcesName": "互动图谱", "resourcesType": 9, "resourcesDistributeType": 7},
        }
        r1_done = dict(r1, studyStatus=1)
        calls = [[r1, r2], [r1_done, r2]]
        client.ai_resources.side_effect = lambda *a, **kw: calls.pop(0)
        client.ai_complete.return_value = {"code": 200}

        row = {"courseName": "人工智能智慧课", "studySpeed": 20, "zhs": {"kind": "ai", "courseId": 1, "classId": 2}}
        handler = ZHSHandler(client=client, course_rows=[row], sleep=lambda _s: None)

        self.assertEqual(len(handler.findings), 1)
        finding = handler.findings[0]
        self.assertEqual(finding["code"], "unverified_unit")
        self.assertEqual(finding["name"], "互动图谱")
        self.assertEqual(finding["kind"], "9/7")
        self.assertIn("resourcesType=9", finding["fields"])

    def test_zhs_unsupported_course_kind_records_finding(self):
        client = Mock()
        row = {"courseName": "未知课型课程", "studySpeed": 10, "zhs": {"kind": "flipped"}}
        handler = ZHSHandler(client=client, course_rows=[row], sleep=lambda _s: None)
        self.assertEqual([f["code"] for f in handler.findings], ["unsupported_course"])


class IssueReportStorageAndSettingsTest(unittest.TestCase):
    def _sample_check(self, *, job_id="j1", course_id="c1", course_name="人工智能导论", kind="vr_lab"):
        return build_issue_check(
            {
                "id": job_id,
                "kind": "study",
                "title": "自动学习",
                "platform": "mooc",
                "course": course_id,
                "course_name": course_name,
                "state": "done",
                "summary": "学习完成",
                "lines": [{"text": "发现未适配资源", "level": "warn", "time": "12:00"}],
            },
            findings=[make_finding("unknown_type", name="虚拟仿真", kind=kind, detail="未适配")],
            course_meta={"type": "AI优课", "kind": "mooc", "progress": 60, "shares": None},
        )

    def test_settings_store_issue_report_toggle_defaults_true_and_validates(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(directory)
            self.assertTrue(store.issue_report())
            store.save_issue_report(False)
            self.assertFalse(store.issue_report())
            store.save_issue_report(True)
            self.assertTrue(store.issue_report())
            with self.assertRaises(SettingsError):
                store.save_issue_report("yes")

    def test_accounts_issue_reports_group_by_fingerprint_and_manage_status(self):
        with tempfile.TemporaryDirectory() as directory:
            accounts = Accounts(directory)
            check1 = self._sample_check(job_id="j1")
            res1 = accounts.submit_issue_report(check1, uid="u1", username="alice", note="第三章卡住")
            self.assertFalse(res1["already_reported"])
            self.assertEqual(res1["report_count"], 1)
            self.assertEqual(res1["reporter_count"], 1)

            # Same user + same job is idempotent
            res_dup = accounts.submit_issue_report(check1, uid="u1", username="alice", note="补充说明")
            self.assertTrue(res_dup["already_reported"])
            self.assertEqual(res_dup["report_count"], 1)

            # Another user hitting the same issue merges into the same row
            check2 = self._sample_check(job_id="j2")
            res2 = accounts.submit_issue_report(check2, uid="u2", username="bob", note="我也卡这里")
            self.assertFalse(res2["already_reported"])
            self.assertEqual(res2["id"], res1["id"])
            self.assertEqual(res2["report_count"], 2)
            self.assertEqual(res2["reporter_count"], 2)

            # Mark resolved, then a third user reports again -> reopens to open
            accounts.set_issue_report_status(res1["id"], "resolved")
            self.assertEqual(accounts.issue_reports()[0]["status"], "resolved")
            check3 = self._sample_check(job_id="j3")
            accounts.submit_issue_report(check3, uid="u3", username="carol")
            rows = accounts.issue_reports()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["status"], "open")
            self.assertEqual(rows[0]["reporter_count"], 3)

            # Ignored stays ignored when reported again
            accounts.set_issue_report_status(res1["id"], "ignored")
            accounts.submit_issue_report(self._sample_check(job_id="j4"), uid="u4", username="dave")
            self.assertEqual(accounts.issue_reports()[0]["status"], "ignored")

            with self.assertRaises(AccountError):
                accounts.set_issue_report_status(res1["id"], "bogus")
            accounts.delete_issue_report(res1["id"])
            self.assertEqual(accounts.issue_reports(), [])
            with self.assertRaises(AccountError):
                accounts.delete_issue_report(res1["id"])

    def test_accounts_auto_collection_upgrades_to_manual_without_double_counting(self):
        with tempfile.TemporaryDirectory() as directory:
            accounts = Accounts(directory)
            check1 = self._sample_check(job_id="j1")

            auto1 = accounts.submit_issue_report(check1, uid="u1", username="alice", source="auto")
            self.assertFalse(auto1["already_reported"])
            self.assertEqual(auto1["source"], "auto")
            self.assertEqual(auto1["report_count"], 1)
            row = accounts.issue_reports()[0]
            self.assertEqual(row["source"], "auto")
            self.assertEqual(row["manual_count"], 0)
            self.assertEqual(row["reporters"][0]["source"], "auto")

            # Same user manually confirms the exact same job with a note -> upgrades without double-counting
            manual1 = accounts.submit_issue_report(check1, uid="u1", username="alice", note="第三章白屏", source="manual")
            self.assertFalse(manual1["already_reported"])
            self.assertEqual(manual1["source"], "manual")
            self.assertEqual(manual1["report_count"], 1)
            row = accounts.issue_reports()[0]
            self.assertEqual(row["source"], "manual")
            self.assertEqual(row["manual_count"], 1)
            self.assertEqual(row["reporters"][0]["note"], "第三章白屏")
            self.assertEqual(row["reporters"][0]["source"], "manual")

            # Re-submitting manually on the same job is idempotent
            manual_dup = accounts.submit_issue_report(check1, uid="u1", username="alice", note="更新备注", source="manual")
            self.assertTrue(manual_dup["already_reported"])
            self.assertEqual(manual_dup["report_count"], 1)

            # Another user retries 3 times automatically -> hit count increments, reporters list stays compact
            for jid in ("j2", "j3", "j4"):
                accounts.submit_issue_report(self._sample_check(job_id=jid), uid="u2", username="bob", source="auto")
            row = accounts.issue_reports()[0]
            self.assertEqual(row["report_count"], 4)
            self.assertEqual(row["reporter_count"], 2)
            self.assertEqual(len(row["reporters"]), 2)
            self.assertEqual({r["username"]: r["source"] for r in row["reporters"]}, {"alice": "manual", "bob": "auto"})

            # Resolved issue hit again automatically reopens; ignored stays ignored
            accounts.set_issue_report_status(auto1["id"], "resolved")
            accounts.submit_issue_report(self._sample_check(job_id="j5"), uid="u3", username="carol", source="auto")
            self.assertEqual(accounts.issue_reports()[0]["status"], "open")

            accounts.set_issue_report_status(auto1["id"], "ignored")
            accounts.submit_issue_report(self._sample_check(job_id="j6"), uid="u4", username="dave", source="auto")
            self.assertEqual(accounts.issue_reports()[0]["status"], "ignored")


class StudiaJobCheckAndHostedFlowTest(unittest.TestCase):
    def _run_stub_job(self, app, target, *, findings=None, state_cancel=False):
        events = []
        orig_publish = app.publish
        app.publish = lambda ev: (events.append(ev), orig_publish(ev))
        job = {
            "id": "job001",
            "kind": "study",
            "title": "自动学习",
            "course": "c1",
            "course_name": "大学英语",
            "platform": "mooc",
            "cancel": threading.Event(),
            "state": "running",
            "summary": "",
            "started": 100.0,
            "ended": None,
            "lines": [],
            "progress": {},
            "findings": list(findings or []),
            "_course_meta": {"type": "AI优课", "kind": "mooc", "progress": 55, "shares": None},
        }
        if state_cancel:
            job["cancel"].set()
        app.jobs[job["id"]] = job
        JOBS[job["id"]] = app
        app._run_job(job, target, None)
        return job, events

    def test_run_job_attaches_issue_check_only_when_enabled_and_relevant(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(directory)
            app = Studia(store)
            finding = make_finding("unknown_type", name="互动环节", kind="h5", detail="未适配")

            job, events = self._run_stub_job(app, lambda: "学习完成", findings=[finding])
            self.assertIsNotNone(job.get("issue_check"))
            self.assertEqual(job["issue_check"]["counts"]["unknown"], 1)
            final_ev = [e for e in events if e.get("type") == "job"][-1]
            self.assertEqual(final_ev["issue_check"]["fingerprint"], job["issue_check"]["fingerprint"])

            # Waiting (captcha) must not produce an adaptation check popup
            def raise_captcha():
                raise CaptchaRequired("需要滑块验证")

            job_wait, _ = self._run_stub_job(app, raise_captcha, findings=[finding])
            self.assertIsNone(job_wait.get("issue_check"))

            # Stopped (cancelled) must not produce an adaptation check popup
            job_stop, _ = self._run_stub_job(app, lambda: "学习完成", findings=[finding], state_cancel=True)
            self.assertIsNone(job_stop.get("issue_check"))

            # Turned off via toggle -> no issue_check attached
            app.save_issue_report({"enabled": False})
            self.assertFalse(app.state()["issue_report"])
            self.assertFalse(app.settings()["issue_report"])
            job_off, _ = self._run_stub_job(app, lambda: "学习完成", findings=[finding])
            self.assertIsNone(job_off.get("issue_check"))

    def test_hosted_issue_report_lifecycle_and_admin_switch(self):
        with tempfile.TemporaryDirectory() as directory:
            hub = Hub(directory, "http://127.0.0.1:8080", key=os.urandom(32))
            access = HostedAccess(hub, 8080)
            req = Mock(headers={}, client_address=("127.0.0.1", 12345))

            admin_id = hub.accounts.create_user("admin", "admin-password", role="admin")
            alice_id = hub.accounts.create_user("alice", "alice-password")
            bob_id = hub.accounts.create_user("bob", "bob-password")
            admin_user = hub.accounts.user(admin_id)
            alice_user = hub.accounts.user(alice_id)
            bob_user = hub.accounts.user(bob_id)

            # Default toggle is ON
            self.assertTrue(hub.site_settings()["issue_report"])
            self.assertTrue(hub.app(alice_id).state()["issue_report"])

            # Hosted user cannot change site-locked toggle via /api/settings/issue-report
            alice_app = hub.app(alice_id)
            self.assertTrue(alice_app.settings()["issue_report_locked"])
            with self.assertRaises(HttpError) as ctx_err:
                alice_app.save_issue_report({"enabled": False})
            self.assertEqual(ctx_err.exception.status, 403)

            # Alice finishes a job with an unhandled resource and submits report
            finding = make_finding("unknown_type", name="互动实验", kind="vr_lab", detail="未适配")
            alice_job, _ = self._run_stub_job(alice_app, lambda: "学习完成", findings=[finding])
            ctx_alice = {"app": alice_app, "user": alice_user, "session": {"csrf": "c"}, "token": "t"}
            res = access.private(req, "POST", "/api/reports", {}, {"job_id": alice_job["id"], "note": "进不去"}, ctx_alice)
            self.assertTrue(res["ok"])
            self.assertEqual(res["reporter_count"], 1)
            self.assertTrue(alice_app.issue_check_for(alice_job["id"])["reported"])

            # Bob hits the same course issue and reports -> merged
            bob_app = hub.app(bob_id)
            bob_job, _ = self._run_stub_job(bob_app, lambda: "学习完成", findings=[finding])
            ctx_bob = {"app": bob_app, "user": bob_user, "session": {"csrf": "c"}, "token": "t"}
            res2 = access.private(req, "POST", "/api/reports", {}, {"job_id": bob_job["id"], "note": "同卡"}, ctx_bob)
            self.assertEqual(res2["id"], res["id"])
            self.assertEqual(res2["reporter_count"], 2)

            # Member cannot read admin reports
            with self.assertRaises(HttpError) as forbidden:
                access.private(req, "GET", "/api/admin/reports", {}, {}, ctx_alice)
            self.assertEqual(forbidden.exception.status, 403)

            # Admin reads, marks resolved, deletes
            ctx_admin = {"app": hub.app(admin_id), "user": admin_user, "session": {"csrf": "c"}, "token": "t"}
            listed = access.private(req, "GET", "/api/admin/reports", {}, {}, ctx_admin)
            self.assertEqual(len(listed["reports"]), 1)
            self.assertEqual(listed["reports"][0]["reporter_count"], 2)

            access.private(req, "POST", "/api/admin/reports/%s/status" % res["id"], {}, {"status": "resolved"}, ctx_admin)
            self.assertEqual(access.private(req, "GET", "/api/admin/reports", {}, {}, ctx_admin)["reports"][0]["status"], "resolved")

            # Admin turns OFF the switch -> state updates and new reports are rejected with 403
            updated = access.private(req, "POST", "/api/admin/settings", {}, {"issue_report": False}, ctx_admin)
            self.assertFalse(updated["issue_report"])
            self.assertFalse(alice_app.state()["issue_report"])
            with self.assertRaises(HttpError) as disabled_err:
                access.private(req, "POST", "/api/reports", {}, {"job_id": alice_job["id"]}, ctx_alice)
            self.assertEqual(disabled_err.exception.status, 403)

            access.private(req, "POST", "/api/admin/reports/%s/delete" % res["id"], {}, {}, ctx_admin)
            self.assertEqual(access.private(req, "GET", "/api/admin/reports", {}, {}, ctx_admin)["reports"], [])

    def test_hosted_silent_auto_collection_and_cross_course_radar(self):
        with tempfile.TemporaryDirectory() as directory:
            hub = Hub(directory, "http://127.0.0.1:8080", key=os.urandom(32))
            access = HostedAccess(hub, 8080)
            req = Mock(headers={}, client_address=("127.0.0.1", 12345))

            admin_id = hub.accounts.create_user("admin", "admin-password", role="admin")
            alice_id = hub.accounts.create_user("alice", "alice-password")
            bob_id = hub.accounts.create_user("bob", "bob-password")
            ctx_admin = {"app": hub.app(admin_id), "user": hub.accounts.user(admin_id), "session": {"csrf": "c"}, "token": "t"}
            ctx_alice = {"app": hub.app(alice_id), "user": hub.accounts.user(alice_id), "session": {"csrf": "c"}, "token": "t"}

            finding = make_finding("unknown_type", name="互动实验", kind="vr_lab", detail="未适配")

            # Alice finishes a job on course c1 and NEVER clicks submit -> already aggregated silently
            alice_app = hub.app(alice_id)
            alice_job, _ = self._run_stub_job(alice_app, lambda: "学习完成", findings=[finding])
            self.assertFalse(alice_app.issue_check_for(alice_job["id"]).get("reported"))

            listed = access.private(req, "GET", "/api/admin/reports", {}, {}, ctx_admin)
            self.assertEqual(len(listed["reports"]), 1)
            self.assertEqual(listed["reports"][0]["source"], "auto")
            self.assertEqual(listed["reports"][0]["report_count"], 1)
            self.assertEqual(len(listed["gaps"]), 1)
            self.assertEqual(listed["gaps"][0]["key"], "mooc|unknown_type|vr_lab")
            self.assertEqual(listed["gaps"][0]["course_count"], 1)

            # Bob hits the same vr_lab gap on a DIFFERENT course c2 without clicking submit
            bob_app = hub.app(bob_id)
            bob_job = {
                "id": "job002",
                "kind": "study",
                "title": "自动学习",
                "course": "c2",
                "course_name": "机械制图",
                "platform": "mooc",
                "cancel": threading.Event(),
                "state": "running",
                "summary": "",
                "started": 200.0,
                "ended": None,
                "lines": [],
                "progress": {},
                "findings": [finding],
                "_course_meta": {"type": "第 2 期开课", "kind": "mooc", "progress": 40, "shares": None},
            }
            bob_app.jobs[bob_job["id"]] = bob_job
            JOBS[bob_job["id"]] = bob_app
            bob_app._run_job(bob_job, lambda: "学习完成", None)

            # Alice later clicks one-click report with a note -> upgrades course c1 row without double-counting
            submit_res = access.private(req, "POST", "/api/reports", {}, {"job_id": alice_job["id"], "note": "进不去"}, ctx_alice)
            self.assertFalse(submit_res["already_reported"])
            self.assertEqual(submit_res["report_count"], 1)
            self.assertEqual(submit_res["source"], "manual")

            listed2 = access.private(req, "GET", "/api/admin/reports", {}, {}, ctx_admin)
            self.assertEqual(len(listed2["reports"]), 2)
            self.assertEqual(len(listed2["gaps"]), 1)
            gap = listed2["gaps"][0]
            self.assertEqual(gap["course_count"], 2)
            self.assertEqual(gap["user_count"], 2)
            self.assertEqual(gap["hit_count"], 2)
            self.assertEqual(gap["manual_count"], 1)
            self.assertEqual(gap["auto_count"], 1)

            # Admin turns OFF switch -> new jobs do not auto-collect
            access.private(req, "POST", "/api/admin/settings", {}, {"issue_report": False}, ctx_admin)
            job3 = dict(bob_job, id="job003", course="c3", course_name="关闭后课程", cancel=threading.Event(),
                        state="running", lines=[], progress={}, findings=[finding])
            bob_app.jobs[job3["id"]] = job3
            JOBS[job3["id"]] = bob_app
            bob_app._run_job(job3, lambda: "学习完成", None)
            self.assertEqual(len(access.private(req, "GET", "/api/admin/reports", {}, {}, ctx_admin)["reports"]), 2)

    def test_answer_records_paper_error_and_skipped_but_ignores_ai_error(self):
        from ai.client import AIConfig

        with tempfile.TemporaryDirectory() as directory:
            app = Studia(SettingsStore(directory))
            platform = app.platform("mooc")
            platform.client = Mock(access_token="tok")
            fake_ai = Mock(session=Mock(), config=AIConfig("https://api.example.com/v1", "gpt-test", "sk-test"))
            app._ai = Mock(return_value=fake_ai)
            course = {"courseId": "c1", "courseName": "高等数学"}
            selected = [
                (course, {"id": "p1", "name": "附件作业1", "typeId": 3}, 1),
                (course, {"id": "p2", "name": "单元测验2", "typeId": 1}, 3),
                (course, {"id": "p3", "name": "章节作业3", "typeId": 1}, 1),
            ]
            outcomes = [
                {"status": "skipped", "message": "附件作业不支持"},
                {"status": "error", "message": "发现未适配题型：连线题"},
                {"status": "ai_error", "message": "401 密钥无效"},
            ]
            job = {
                "id": "ans1",
                "kind": "answer",
                "title": "AI 答题",
                "course": "c1",
                "course_name": "高等数学",
                "platform": "mooc",
                "cancel": threading.Event(),
                "lines": [],
                "findings": [],
            }
            fake_runner = Mock()
            fake_runner.run_paper.side_effect = outcomes
            with unittest.mock.patch("web.server.AnswerRunner", return_value=fake_runner):
                app._answer(platform, selected, True, job)
            codes = [(f["code"], f["name"]) for f in job["findings"]]
            self.assertEqual(codes, [("paper_skipped", "附件作业1"), ("paper_error", "单元测验2")])


if __name__ == "__main__":
    unittest.main()
