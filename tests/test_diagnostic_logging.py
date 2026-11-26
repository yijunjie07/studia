import logging
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import core.log
from ai.runner import AnswerRunner
from core.api_client import BaseAPIClient
from core.study import check_study_response, run_resources
from mooc.activities import CourseActivities
from mooc.exam_api import ExamAPI, ExamError
from mooc.main import AIMoocHandler
from web.server import JOBS, Platform, Studia
from zhs.answer import ZHSAnswerRunner, catalog_ai
from zhs.main import ZHSHandler


class _ListHandler(logging.Handler):
    def __init__(self, level=logging.DEBUG):
        super().__init__(level)
        self.records = []

    def emit(self, record):
        self.records.append(record)

    @property
    def messages(self):
        return [r.getMessage() for r in self.records]


def _capture(logger_name, level=logging.DEBUG):
    log = logging.getLogger(logger_name)
    handler = _ListHandler(level)
    log.addHandler(handler)
    return log, handler


class SummarizeFieldsTest(unittest.TestCase):
    def test_summarize_fields_redacts_secrets_and_lists_extra_keys(self):
        text = core.log.summarize_fields(
            {
                "id": "e1",
                "typeId": 3,
                "token": "secret-tok",
                "password": "pw",
                "submitFileLimit": 2,
                "extraPayload": {"nested": 1},
            },
            keys=("id", "typeId"),
        )
        self.assertIn("id=e1", text)
        self.assertIn("typeId=3", text)
        self.assertNotIn("secret-tok", text)
        self.assertNotIn("pw", text)
        self.assertIn("submitFileLimit", text)


class RequestAndJobContextLoggingTest(unittest.TestCase):
    def test_request_thread_context_tags_daily_log_with_username(self):
        from web.server import set_request_owner

        with tempfile.TemporaryDirectory() as directory:
            cwd = os.getcwd()
            os.chdir(directory)
            log = logging.getLogger("web.request-context-test")
            log.setLevel(logging.INFO)
            handler = core.log.DailyFileHandler()
            handler.setFormatter(logging.Formatter("[%(levelname)s]%(who)s :: %(message)s"))
            log.addHandler(handler)
            try:
                set_request_owner("bob")
                log.warning("列表异常")
                set_request_owner(None)
                log.warning("无用户")
            finally:
                set_request_owner(None)
                log.removeHandler(handler)
                handler.close()
                os.chdir(cwd)
            lines = next(Path(directory).glob("*.log")).read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines, ["[WARNING][bob] :: 列表异常", "[WARNING] :: 无用户"])

    def test_run_job_logs_start_and_finish_with_platform_course_and_outcome(self):
        app = Studia.__new__(Studia)
        app.owner = "alice"
        app.lock = threading.RLock()
        app.history = []
        app.last = {}
        app.jobs = {}
        app.store = None
        app.closing = False
        app.publish = lambda event: None
        app.job_limit = lambda: 2
        app._forget = lambda platform, cid: None
        app.save_sessions = lambda platform=None: None

        job = {
            "id": "j1234567",
            "kind": "answer",
            "title": "AI 答题",
            "course": "c-100",
            "course_name": "大学英语",
            "platform": "mooc",
            "papers": ["附件作业1", "单元测验2"],
            "state": "running",
            "summary": "",
            "started": 1.0,
            "ended": None,
            "lines": [],
            "cancel": threading.Event(),
        }
        app.jobs[job["id"]] = job
        JOBS[job["id"]] = app

        log, handler = _capture("web.server")
        try:
            app._run_job(job, lambda: "处理完成 1/2 份试卷", None)
        finally:
            log.removeHandler(handler)
            JOBS.pop(job["id"], None)

        joined = "\n".join(handler.messages)
        self.assertIn("任务开始", joined)
        self.assertIn("MOOC", joined)
        self.assertIn("大学英语", joined)
        self.assertIn("附件作业1", joined)
        self.assertIn("任务结束", joined)
        self.assertIn("处理完成 1/2 份试卷", joined)

    def test_read_tasks_logs_warning_with_raw_fields_for_attachment_homework(self):
        app = Studia.__new__(Studia)
        app.owner = "alice"
        app.lock = threading.RLock()
        app.client = lambda platform: Mock()
        platform = Platform("mooc")
        row = {"courseName": "职业素养", "courseId": "c1", "id": "ci1"}
        attachment_item = {
            "id": "att-1",
            "examId": "att-1",
            "name": "实践报告提交",
            "typeId": 3,
            "questionSettingMethod": 3,
            "status": 0,
            "answerCount": 1,
            "fileUploadRequired": True,
            "_completion_status": "not_started",
        }
        log, handler = _capture("web.server", logging.INFO)
        try:
            with patch("web.server._mooc_catalog", return_value=[(row, attachment_item, 1)]):
                app._read_tasks(platform, row)
        finally:
            log.removeHandler(handler)

        warnings = [r.getMessage() for r in handler.records if r.levelno >= logging.WARNING]
        self.assertTrue(warnings, f"Expected warning for attachment task, got: {handler.messages}")
        msg = "\n".join(warnings)
        self.assertIn("MOOC", msg)
        self.assertIn("职业素养", msg)
        self.assertIn("实践报告提交", msg)
        self.assertIn("暂不支持", msg)
        self.assertIn("typeId=3", msg)

    def test_exam_captcha_logs_warning_when_blocked_by_entry_check(self):
        from zhs.answer import EntryCheck
        from web.server import HttpError

        app = Studia.__new__(Studia)
        app.owner = "alice"
        app.lock = threading.RLock()
        platform = Platform("zhs")
        platform.rows = [{"courseName": "形式与政策", "zhs": {"kind": "shared", "courseId": 99}}]
        platform.entries["shared-99"] = {
            "sex-1-2": (
                platform.rows[0],
                {
                    "id": "sex-1-2",
                    "name": "期末考试",
                    "_captcha": True,
                    "_entry": {"start": True, "remain": 1, "reviewType": 0},
                    "zhs": {"courseId": 99, "examId": 2, "recruitId": 3, "stuExamId": 1},
                },
                2,
            )
        }
        app.platform = lambda pid: platform
        app.client = lambda p: Mock()

        log, handler = _capture("web.server", logging.WARNING)
        try:
            with patch("web.server.exam_entry_check", return_value=EntryCheck(blocked="学校开了人脸识别，只能到平台网页开考。")):
                with self.assertRaises(HttpError):
                    app.exam_captcha("zhs", "shared-99", "sex-1-2")
        finally:
            log.removeHandler(handler)

        msg = "\n".join(handler.messages)
        self.assertIn("智慧树", msg)
        self.assertIn("形式与政策", msg)
        self.assertIn("期末考试", msg)
        self.assertIn("人脸识别", msg)


class MoocDiagnosticLoggingTest(unittest.TestCase):
    def test_check_study_response_includes_platform_code_and_msg(self):
        with self.assertRaises(RuntimeError) as ctx:
            check_study_response({"code": 500, "msg": "该节点需要提交文件"})
        self.assertIn("500", str(ctx.exception))
        self.assertIn("该节点需要提交文件", str(ctx.exception))

    def test_mooc_handle_resource_error_logs_course_resource_type_and_node_fields(self):
        client = Mock()
        client.study_design_list.return_value = [{"id": "ch1", "name": "第一章"}]
        client.study_record_list.return_value = []
        client.get_cell_list.return_value = [
            {
                "id": "node-99",
                "courseId": "c1",
                "courseInfoId": "ci1",
                "name": "上传实验报告",
                "fileType": "文件提交",
                "cellType": 9,
                "fileUrl": "",
            }
        ]
        client.study_record.return_value = {"code": 500, "msg": "不支持该资源类型"}

        log, handler = _capture("mooc.main")
        try:
            AIMoocHandler(
                client=client,
                course_rows=[{"id": "ci1", "courseId": "c1", "courseName": "高等数学"}],
                max_workers=1,
            )
        finally:
            log.removeHandler(handler)

        errors = [r.getMessage() for r in handler.records if r.levelno >= logging.ERROR]
        self.assertTrue(errors, f"Expected error log, got: {handler.messages}")
        msg = "\n".join(errors)
        self.assertIn("MOOC", msg)
        self.assertIn("高等数学", msg)
        self.assertIn("上传实验报告", msg)
        self.assertIn("文件提交", msg)
        self.assertIn("node-99", msg)
        self.assertIn("不支持该资源类型", msg)

    def test_mooc_activities_discussion_error_includes_course_name(self):
        client = Mock()
        client.discussion_list.return_value = {"code": 500, "msg": "讨论区关闭"}
        client.course_evaluation.return_value = {"code": 200, "data": {"id": 1}}
        log, handler = _capture("mooc.activities.test")
        try:
            CourseActivities(client, Mock(), log=log).run_course(
                {"courseId": "c1", "id": "ci1", "courseName": "商务礼仪"}
            )
        finally:
            log.removeHandler(handler)

        errors = "\n".join(r.getMessage() for r in handler.records if r.levelno >= logging.ERROR)
        self.assertIn("商务礼仪", errors)

    def test_base_api_client_error_logs_endpoint(self):
        client = BaseAPIClient("https://example.test")
        response = Mock(status_code=500)
        log, handler = _capture("core.api_client")
        try:
            with patch.object(client.session, "get", return_value=response):
                result = client.get("/course/cell/list")
        finally:
            log.removeHandler(handler)
            client.close()
        self.assertIsNone(result)
        msg = "\n".join(handler.messages)
        self.assertIn("500", msg)
        self.assertIn("/course/cell/list", msg)

    def test_mooc_exam_api_logs_diagnostic_warning_on_error_code(self):
        client = Mock(user_id="u1", default_base_url="https://example.test", access_token="tok")
        session = Mock()
        session.headers = {}
        resp = Mock(status_code=200)
        resp.json.return_value = {"code": 500, "msg": "附件作业不支持此接口", "extra": 1}
        session.request.return_value = resp
        api = ExamAPI(client, session=session)

        log, handler = _capture("mooc.exam_api")
        try:
            with self.assertRaises(ExamError):
                api.request("GET", "/course/exam/paper", params={"id": "p1"})
        finally:
            log.removeHandler(handler)

        warnings = "\n".join(r.getMessage() for r in handler.records if r.levelno >= logging.WARNING)
        self.assertIn("/course/exam/paper", warnings)
        self.assertIn("500", warnings)
        self.assertIn("附件作业不支持此接口", warnings)

    def test_mooc_answer_runner_logs_warning_with_course_paper_and_question_details(self):
        api = Mock(user_id="u1")
        api.records.return_value = []
        api.paper.return_value = {
            "name": "实验二",
            "questionCount": 1,
            "taskExamRecord": {"id": "t1", "status": "0", "userId": "u1"},
            "questions": [
                {"id": "q1", "typeId": 12, "typeName": "文件上传题", "title": "请上传实验代码压缩包"}
            ],
        }
        ai = Mock()
        ai.config = Mock(model="test-model")
        with tempfile.TemporaryDirectory() as directory:
            runner = AnswerRunner(api, ai, output_dir=directory, auto_submit=True)
            log, handler = _capture("ai.runner")
            try:
                report = runner.run_paper(
                    {"id": "ci1", "courseId": "c1", "courseName": "Python程序设计"},
                    {"id": "e1", "name": "实验二"},
                    1,
                )
            finally:
                log.removeHandler(handler)

        self.assertEqual(report["status"], "needs_review")
        warnings = "\n".join(r.getMessage() for r in handler.records if r.levelno >= logging.WARNING)
        self.assertIn("Python程序设计", warnings)
        self.assertIn("实验二", warnings)
        self.assertIn("暂不支持题型 12", warnings)
        self.assertIn("文件上传题", warnings)


class ZhsDiagnosticLoggingTest(unittest.TestCase):
    def test_zhs_answer_runner_logs_course_name_and_raw_question_type_on_unsupported_question(self):
        client = Mock()
        client.exam_open.return_value = {}
        client.exam_sheet.return_value = [{"questionId": 101, "version": 1}]
        client.exam_question.return_value = {
            "id": 101,
            "content": "请上传作品附件",
            "questionType": {"id": 9, "name": "附件上传题"},
        }
        runner = ZHSAnswerRunner(client, Mock(), auto_submit=True, sleep=lambda _: None)
        course = {"courseName": "数字媒体设计", "zhs": {"kind": "ai", "courseId": 10, "classId": 20}}
        item = {
            "id": "hw-1-2-3",
            "name": "知识点一 · 作业",
            "zhs": {"kind": "ai_homework", "courseId": 10, "knowledgeId": 1, "examTestId": 2, "paperId": 3},
        }

        log, handler = _capture("zhs.answer")
        try:
            result = runner.run_paper(course, item, 1)
        finally:
            log.removeHandler(handler)

        self.assertEqual(result["status"], "error")
        warnings = "\n".join(r.getMessage() for r in handler.records if r.levelno >= logging.WARNING)
        self.assertIn("数字媒体设计", warnings)
        self.assertIn("知识点一 · 作业", warnings)
        self.assertIn("暂不支持题型 9", warnings)
        self.assertIn("附件上传题", warnings)

    def test_zhs_catalog_ai_warnings_include_course_name(self):
        client = Mock()
        client.ai_course_basic.return_value = {
            "cakeThemeList": [{"knowledgeList": [{"knowledgeId": 1, "knowledgeName": "导论"}]}]
        }
        client.ai_homework_info.side_effect = RuntimeError("接口异常")
        client.ai_exam_tasks.return_value = []
        course = {"courseName": "机器学习基础", "zhs": {"kind": "ai", "courseId": 1, "classId": 2}}

        log, handler = _capture("zhs.answer")
        try:
            catalog_ai(client, course)
        finally:
            log.removeHandler(handler)

        warnings = "\n".join(r.getMessage() for r in handler.records if r.levelno >= logging.WARNING)
        self.assertIn("机器学习基础", warnings)
        self.assertIn("导论", warnings)

    def test_zhs_study_ai_logs_resource_type_fields_on_failure(self):
        client = Mock()
        client.ai_course_basic.return_value = {
            "cakeThemeList": [{"knowledgeList": [{"knowledgeId": 1, "knowledgeName": "第一章"}]}]
        }
        client.ai_resources.return_value = [
            {
                "studyStatus": 0,
                "resourcesType": 7,
                "resourcesDistributeType": 4,
                "resourcesDetail": {
                    "resourcesName": "提交课后文件",
                    "resourcesType": 7,
                    "resourcesDistributeType": 4,
                },
            }
        ]

        log, handler = _capture("zhs.main")
        try:
            ZHSHandler(
                client=client,
                course_rows=[{"courseName": "工业设计", "zhs": {"kind": "ai", "courseId": 1, "classId": 2}}],
                sleep=lambda _: None,
            )
        finally:
            log.removeHandler(handler)

        errors = "\n".join(r.getMessage() for r in handler.records if r.levelno >= logging.ERROR)
        self.assertIn("工业设计", errors)
        self.assertIn("提交课后文件", errors)
        self.assertIn("resourcesType=7", errors)
        self.assertIn("resourcesDistributeType=4", errors)


if __name__ == "__main__":
    unittest.main()
