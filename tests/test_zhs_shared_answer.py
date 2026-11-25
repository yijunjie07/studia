import io
import random
import unittest

from core.auth import PlatformUnavailable
from core.task_capabilities import task_availability
from zhs.answer import ZHSAnswerRunner, catalog, catalog_shared, encode, exam_entry_check, prepare_shared
from zhs.api import CaptchaRequired, ZHSApiError


class FixedRng(random.Random):
    def uniform(self, a, b):
        return a


def shared_question(eid, kind=1, name="1+1=?", options=None):
    if options is None:
        options = [{"id": 101, "content": "1"}, {"id": 102, "content": "2"}]
    return {"eid": eid, "name": name, "questionType": kind, "questionOptions": options}


class FakeAI:
    def __init__(self, answers):
        self.answers = list(answers)
        self.asked = []

    def answer(self, question):
        self.asked.append(question)
        result = self.answers.pop(0)
        if isinstance(result, Exception):
            raise result
        return {"answer": result, "explanation": ""}


class FakeSharedClient:
    def __init__(self, questions, *, homework_rows=None, exam_rows=None, lock=1,
                 school="88", submit_score=None):
        self.questions = list(questions)
        self.homework_rows = homework_rows if homework_rows is not None else [
            {"id": 100, "examId": 200, "examName": "第一次作业", "state": 1,
             "score": 0, "totalScore": 20, "startTime": "a", "endDate": "b", "courseId": 3},
        ]
        self.exam_rows = exam_rows if exam_rows is not None else [
            {"id": 300, "examId": 400, "examName": "期末考试", "state": 2,
             "studentStartTime": "s", "faStudentExamRemainCount": 3, "courseId": 3},
        ]
        self.lock = lock
        self.school = school
        self.submit_score = submit_score
        self.calls = []

    def _record(self, name, payload=None):
        self.calls.append((name, payload))

    def shared_exam_sso(self):
        self._record("shared_exam_sso")

    def shared_school_id(self):
        self._record("shared_school_id")
        return self.school

    def shared_homework_list(self, recruit_id, course_id, flag):
        self._record("shared_homework_list", flag)
        return [dict(row) for row in self.homework_rows] if flag == 1 else []

    def shared_exam_list(self, recruit_id, course_id, flag):
        self._record("shared_exam_list", flag)
        return [dict(row) for row in self.exam_rows] if flag == 1 else []

    def shared_answer_lock(self, exam_id, recruit_id):
        self._record("shared_answer_lock", exam_id)
        return self.lock.get(exam_id, 1) if isinstance(self.lock, dict) else self.lock

    def shared_do_homework(self, recruit_id, exam_id, stu_exam_id, school_id, course_id):
        self._record("shared_do_homework",
                     (recruit_id, exam_id, stu_exam_id, school_id, course_id))
        return {"examBase": {"workExamParts": [{"questionDtos": self.questions}]}}

    def shared_do_exam(self, recruit_id, exam_id, stu_exam_id, school_id, course_id):
        self._record("shared_do_exam",
                     (recruit_id, exam_id, stu_exam_id, school_id, course_id))
        if getattr(self, "refuse", None) is not None:
            raise ZHSApiError("-1", self.refuse)
        return {"examBase": {"workExamParts": [{"questionDtos": self.questions}]}}

    def shared_save_answer(self, answer_item, recruit_id, *, exam, captcha_vision=None):
        self._record("shared_save_answer", {"item": answer_item, "recruitId": recruit_id,
                                            "exam": exam, "captcha_vision": captcha_vision})

    def shared_submit_homework(self, recruit_id, exam_id, stu_exam_id, count):
        self._record("shared_submit_homework", count)
        return self.submit_score or {"score": 18, "totalScore": 20}

    def shared_submit_exam(self, recruit_id, exam_id, stu_exam_id, count):
        self._record("shared_submit_exam", count)
        return {"statu": "1"}

    def shared_redo_homework(self, recruit_id, exam_id, course_id):
        self._record("shared_redo_homework", (recruit_id, exam_id, course_id))
        return {"rt": True}

    # The platform's checks before an exam's entry code; by default the school asks for nothing more.
    entry = {"exception": {"examStatus": 1}, "limit": 1, "rule": {"progress": 1, "progressRule": 36},
             "location": False, "located": True, "face": False}

    def shared_exception_action(self, recruit_id, school_id):
        self._record("shared_exception_action", (recruit_id, school_id))
        return self.entry["exception"]

    def shared_limit_time(self, exam_id, recruit_id):
        self._record("shared_limit_time", exam_id)
        return self.entry["limit"]

    def shared_progress_rule(self, recruit_id, school_id):
        self._record("shared_progress_rule", school_id)
        return self.entry["rule"]

    def shared_location_on(self, course_id, recruit_id, school_id):
        self._record("shared_location_on", course_id)
        return self.entry["location"]

    def shared_location_passed(self, course_id, exam_id):
        self._record("shared_location_passed", exam_id)
        return self.entry["located"]

    def shared_face_on(self, recruit_id, school_id):
        self._record("shared_face_on", school_id)
        return self.entry["face"]

    def names(self):
        return [name for name, _ in self.calls]

    def call(self, name):
        return [payload for called, payload in self.calls if called == name]


COURSE = {"courseName": "共享课", "zhs": {"kind": "shared", "recruitId": 9, "courseId": 3}}


def homework_item():
    return {"id": "shw-100-200", "name": "第一次作业",
            "zhs": {"kind": "shared_homework", "recruitId": 9, "courseId": 3,
                    "stuExamId": 100, "examId": 200}}


def exam_item():
    return {"id": "sex-300-400", "name": "期末考试",
            "zhs": {"kind": "shared_exam", "recruitId": 9, "courseId": 3,
                    "stuExamId": 300, "examId": 400}}


def runner(client, ai, auto_submit=True):
    return ZHSAnswerRunner(client, ai, auto_submit=auto_submit,
                           sleep=lambda seconds: None, rng=FixedRng())


class PrepareSharedTest(unittest.TestCase):
    def test_question_type_dict_or_number(self):
        prepared = prepare_shared(shared_question("e1", {"id": 1, "name": "单选题"}))
        self.assertEqual(prepared["qid"], "e1")
        self.assertEqual(prepared["kind"], 1)
        self.assertEqual(prepared["ids"], {"A": 101, "B": 102})
        self.assertEqual(prepare_shared(shared_question("e2", "2"))["kind"], 2)

    def test_missing_eid(self):
        raw = shared_question(None)
        with self.assertRaises(ValueError):
            prepare_shared(raw)
        del raw["eid"]
        with self.assertRaises(ValueError):
            prepare_shared(raw)

    def test_media_option_validation_reused(self):
        with self.assertRaises(ValueError):
            prepare_shared(shared_question("e3", name='<img src="x.png">'))

    def test_answer_encoding(self):
        single = prepare_shared(shared_question("e1"))
        self.assertEqual(",".join(str(x) for x in encode(single, "B", fill_sep="/")), "102")
        multi = prepare_shared(shared_question("e2", kind={"id": 2, "name": "多选题"}))
        self.assertEqual(",".join(str(x) for x in encode(multi, ["B", "A"], fill_sep="/")),
                         "102,101")
        fill = prepare_shared(shared_question("e3", kind=3, options=[{}, {}]))
        self.assertEqual(encode(fill, ["x", "y"], fill_sep="/"), ["x/y"])


class SharedHomeworkFlowTest(unittest.TestCase):
    def test_full_flow(self):
        client = FakeSharedClient([
            shared_question("e1"),
            shared_question("e2", kind=2),
            shared_question("e3", kind=3, options=[{}, {}]),
        ])
        ai = FakeAI(["B", ["A", "B"], ["x", "y"]])
        result = runner(client, ai).run_paper(COURSE, homework_item(), 1)
        self.assertEqual(result["status"], "submitted", result)
        self.assertIn("得分 18/20", result["message"])
        names = client.names()
        self.assertEqual(names[0], "shared_exam_sso")
        self.assertLess(names.index("shared_do_homework"), names.index("shared_save_answer"))
        self.assertEqual(len(client.call("shared_school_id")), 1)
        self.assertEqual(
            client.call("shared_do_homework")[0], (9, 200, 100, "88", 3))
        saved = [call["item"] for call in client.call("shared_save_answer")]
        self.assertEqual([item["answer"] for item in saved], ["102", "101,102", "x/y"])
        self.assertEqual([item["eid"] for item in saved], ["e1", "e2", "e3"])
        self.assertEqual([item["questionType"] for item in saved], [1, 2, 3])
        first = saved[0]
        self.assertEqual(first["examType"], "")
        self.assertEqual(first["fromType"], 3)
        self.assertEqual(first["schoolId"], "88")
        self.assertEqual(first["deviceId"], "")
        self.assertEqual(first["dataIds"], "")
        self.assertEqual(first["stuExamId"], 100)
        self.assertEqual(first["examId"], 200)
        self.assertEqual(first["recruitId"], 9)
        self.assertFalse(client.call("shared_save_answer")[0]["exam"])
        self.assertEqual(client.call("shared_submit_homework"), [3])

    def test_preview_does_not_submit(self):
        client = FakeSharedClient([shared_question("e1")])
        ai = FakeAI(["B"])
        result = runner(client, ai, auto_submit=False).run_paper(
            COURSE, homework_item(), 1)
        self.assertEqual(result["status"], "preview")
        self.assertIs(client.call("shared_save_answer")[0]["captcha_vision"], ai)
        self.assertNotIn("shared_submit_homework", client.names())

    def test_unusable_answers_end_in_a_random_option_not_a_blank(self):
        client = FakeSharedClient([shared_question("e1"), shared_question("e2"),
                                   shared_question("e3")])
        runner(client, FakeAI(["Z"] * 9)).run_paper(COURSE, homework_item(), 1)
        self.assertEqual(len(client.call("shared_save_answer")), 3)

    def test_captcha_propagates(self):
        client = FakeSharedClient([shared_question("e1")])

        def slider(answer_item, recruit_id, *, exam, captcha_vision=None):
            raise CaptchaRequired("滑块")

        client.shared_save_answer = slider
        with self.assertRaises(CaptchaRequired):
            runner(client, FakeAI(["B"])).run_paper(COURSE, homework_item(), 1)

    def test_submit_failure_is_unknown(self):
        client = FakeSharedClient([shared_question("e1")])

        def down(*args):
            raise PlatformUnavailable("down")

        client.shared_submit_homework = down
        result = runner(client, FakeAI(["B"])).run_paper(COURSE, homework_item(), 1)
        self.assertEqual(result["status"], "submission_unknown")
        self.assertIn("未重试", result["message"])
        self.assertEqual(client.names().count("shared_submit_homework"), 0)

    def test_recheck_sees_submitted_paper(self):
        client = FakeSharedClient([shared_question("e1")])
        client.homework_rows = [dict(client.homework_rows[0], state=4,
                                     score=20, totalScore=20)]
        result = runner(client, FakeAI(["B"])).run_paper(COURSE, homework_item(), 1)
        self.assertEqual(result["status"], "error")
        self.assertIn("已满分", result["message"])
        self.assertNotIn("shared_do_homework", client.names())

    def test_empty_paper(self):
        client = FakeSharedClient([])
        result = runner(client, FakeAI([])).run_paper(COURSE, homework_item(), 1)
        self.assertEqual(result["status"], "error")


class SharedHomeworkRedoFlowTest(unittest.TestCase):
    def redo_client(self, questions=None):
        client = FakeSharedClient(questions if questions is not None else [shared_question("e1")])
        client.homework_rows = [{"id": 100, "examId": 200, "examName": "第一次作业",
                                 "state": 4, "score": 12, "totalScore": 20,
                                 "backNum": 2, "isMarking": 1, "courseId": 3}]
        return client

    def test_redo_is_requested_before_do_homework(self):
        client = self.redo_client()
        result = runner(client, FakeAI(["B"])).run_paper(COURSE, homework_item(), 1)
        self.assertEqual(result["status"], "submitted", result)
        names = client.names()
        self.assertEqual(client.call("shared_redo_homework"), [(9, 200, 3)])
        self.assertLess(names.index("shared_redo_homework"), names.index("shared_do_homework"))

    def test_redo_failure_stops_before_do_homework(self):
        client = self.redo_client()

        def down(*args):
            raise PlatformUnavailable("down")

        client.shared_redo_homework = down
        result = runner(client, FakeAI(["B"])).run_paper(COURSE, homework_item(), 1)
        self.assertEqual(result["status"], "error")
        self.assertIn("申请重做失败", result["message"])
        self.assertNotIn("shared_do_homework", client.names())

    def test_ai_failure_after_redo_notes_consumed_attempt(self):
        client = self.redo_client([shared_question("e1")])
        result = runner(client, FakeAI(["Z"])).run_paper(COURSE, homework_item(), 1)
        self.assertEqual(result["status"], "error")
        self.assertIn("已消耗一次重做机会", result["message"])
        self.assertNotIn("shared_submit_homework", client.names())

    def test_exam_never_requests_redo(self):
        client = FakeSharedClient([shared_question("e1")])
        client.homework_rows = []
        client.exam_rows = [{"id": 300, "examId": 400, "examName": "期末", "state": 2,
                             "studentStartTime": "s", "faStudentExamRemainCount": 3, "courseId": 3}]
        runner(client, FakeAI(["B"])).run_paper(COURSE, exam_item(), 2)
        self.assertNotIn("shared_redo_homework", client.names())


class PapersHintTest(unittest.TestCase):
    def test_selectable_redo_item_shows_hint(self):
        from unittest.mock import patch
        from rich.console import Console
        from terminal import theme
        from terminal.ui import TerminalUI

        view = TerminalUI(console=Console(file=io.StringIO(), theme=theme.THEME, width=120))
        task = (COURSE, {"id": "shw-1-2", "name": "作业",
                         "_hint": "重做成绩会覆盖当前成绩"}, 1)
        with patch.object(TerminalUI, "select", return_value=[]) as select:
            view.papers([task])
        hint = select.call_args.kwargs["item_hint"]
        self.assertEqual(hint(task), "重做成绩会覆盖当前成绩")


class SharedExamFlowTest(unittest.TestCase):
    def test_exam_saves_with_exam_flag(self):
        client = FakeSharedClient([shared_question("e1")])
        result = runner(client, FakeAI(["B"])).run_paper(COURSE, exam_item(), 2)
        self.assertEqual(result["status"], "submitted", result)
        self.assertIn("成绩以平台为准", result["message"])
        self.assertEqual(client.call("shared_do_exam")[0], (9, 400, 300, "88", 3))
        saved = client.call("shared_save_answer")[0]
        self.assertTrue(saved["exam"])
        self.assertEqual(saved["item"]["examType"], 1)
        self.assertEqual(client.call("shared_submit_exam"), [1])

    def test_recheck_sees_barred_exam(self):
        client = FakeSharedClient([shared_question("e1")], lock=3)
        result = runner(client, FakeAI(["B"])).run_paper(COURSE, exam_item(), 2)
        self.assertEqual(result["status"], "error")
        self.assertIn("禁止考试", result["message"])
        self.assertNotIn("shared_do_exam", client.names())

    def test_exam_entered_without_its_picture_code_says_so(self):
        # What the real final exam answered: doExam status -1, msg 3 (验证码是否通过异常 on the platform's page).
        client = FakeSharedClient([shared_question("e1")])
        client.refuse = 3
        result = runner(client, FakeAI(["B"])).run_paper(COURSE, exam_item(), 2)
        self.assertEqual(result["status"], "error")
        self.assertIn("验证码", result["message"])
        self.assertNotIn("-1", result["message"])
        self.assertNotIn("shared_save_answer", client.names())

    def test_other_exam_refusals_keep_the_platform_text(self):
        client = FakeSharedClient([shared_question("e1")])
        client.refuse = "考点考试异常"
        result = runner(client, FakeAI(["B"])).run_paper(COURSE, exam_item(), 2)
        self.assertEqual(result["status"], "error")
        self.assertIn("考点考试异常", result["message"])

    def test_recheck_sends_identity_check_to_the_platform(self):
        client = FakeSharedClient([shared_question("e1")], lock=2)
        result = runner(client, FakeAI(["B"])).run_paper(COURSE, exam_item(), 2)
        self.assertEqual(result["status"], "error")
        self.assertIn("身份验证", result["message"])
        self.assertNotIn("shared_do_exam", client.names())



class ExamEntryCheckTest(unittest.TestCase):
    """The platform's checks before it shows an exam's entry code, as its exam list makes them."""

    def item(self, start=True, parent=None, review=0):
        return dict(exam_item(), _entry={"start": start, "remain": 1, "parentId": parent, "reviewType": review})

    def check(self, start=True, **entry):
        client = FakeSharedClient([])
        client.entry = dict(FakeSharedClient.entry, **entry)
        return exam_entry_check(client, self.item(start)), client

    def test_nothing_more_asked_lets_the_code_show(self):
        check, client = self.check()
        self.assertEqual((check.blocked, check.warning, check.location), ("", "", False))
        self.assertEqual(client.names(), ["shared_exam_sso", "shared_school_id", "shared_exception_action",
                                          "shared_limit_time", "shared_progress_rule", "shared_location_on",
                                          "shared_face_on"])

    def test_continuing_an_exam_skips_the_progress_rule(self):
        check, client = self.check(start=False, rule={"progress": 0, "progressRule": 36})
        self.assertEqual((check.blocked, check.location), ("", False))
        self.assertNotIn("shared_progress_rule", client.names())

    def test_each_requirement_that_needs_the_platforms_page(self):
        cases = [
            ({"exception": {"examStatus": 3}}, "异常"),
            ({"exception": {}}, "异常"),
            ({"limit": False}, "作答时间已经结束"),
            ({"rule": {"progress": 0, "progressRule": 36}}, "学习进度达到 36%"),
            ({"face": True}, "人脸识别"),
        ]
        for entry, words in cases:
            with self.subTest(entry=entry):
                check, _ = self.check(**entry)
                self.assertIn(words, check.blocked)
                self.assertFalse(check.location)
        # Location scan is done right inside Studia before checking face / showing the picture code.
        need_loc, client = self.check(location=True, located=False)
        self.assertEqual((need_loc.blocked, need_loc.location), ("", True))
        self.assertNotIn("shared_face_on", client.names())
        passed, _ = self.check(location=True, located=True)
        self.assertEqual((passed.blocked, passed.location), ("", False))

    def test_old_exam_system_and_makeup_exams(self):
        client = FakeSharedClient([])
        check = exam_entry_check(client, self.item(review=1))
        self.assertIn("旧版考试系统", check.blocked)
        client.entry = dict(FakeSharedClient.entry, exception={"examStatus": 1, "makeUpExamStatus": 3})
        check = exam_entry_check(client, self.item(parent=99))
        self.assertIn("异常", check.blocked)  # a make-up exam reads its own status

    def test_a_reset_exam_warns_but_goes_on(self):
        check, _ = self.check(exception={"examStatus": 2})
        self.assertEqual((check.blocked, check.location), ("", False))
        self.assertIn("0 分", check.warning)


class CatalogSharedTest(unittest.TestCase):
    def make_client(self, **kwargs):
        client = FakeSharedClient([], **kwargs)
        return client

    def test_entries_and_ids(self):
        client = self.make_client()
        entries = catalog(client, COURSE)
        self.assertEqual(client.names()[0], "shared_exam_sso")
        self.assertEqual([category for _, _, category in entries], [1, 2])
        homework = entries[0][1]
        self.assertEqual(homework["id"], "shw-100-200")
        self.assertEqual(homework["zhs"], {"kind": "shared_homework", "recruitId": 9,
                                           "courseId": 3, "stuExamId": 100, "examId": 200})
        self.assertEqual(homework["_completion_status"], "not_started")
        self.assertNotIn("_unavailable", homework)
        self.assertEqual(homework["endTime"], "b")
        exam = entries[1][1]
        self.assertEqual(exam["id"], "sex-300-400")
        for _, item, _ in entries:
            self.assertNotIn("typeId", item)
            self.assertNotIn("status", item)

    def test_homework_unavailable_states(self):
        client = self.make_client()
        client.homework_rows = [
            {"id": 1, "examId": 11, "examName": "已交", "state": 4, "score": 100, "courseId": 3},
            {"id": 2, "examId": 12, "examName": "怪状态", "state": 9, "courseId": 3},
            {"id": 3, "examId": 13, "examName": "重置", "state": 5, "courseId": 3},
        ]
        client.exam_rows = []
        entries = catalog(client, COURSE)
        by_id = {item["id"]: item for _, item, _ in entries}
        self.assertEqual(by_id["shw-1-11"]["_unavailable"][0], "无重做次数")
        self.assertEqual(by_id["shw-1-11"]["_completion_status"], "submitted")
        self.assertEqual(by_id["shw-2-12"]["_unavailable"][0], "状态未知")
        self.assertNotIn("_unavailable", by_id["shw-3-13"])
        self.assertEqual(task_availability(by_id["shw-1-11"], 1).label, "无重做次数")

    def test_homework_redo_states(self):
        client = self.make_client()
        client.homework_rows = [
            {"id": 1, "examId": 11, "examName": "满分", "state": 4,
             "score": "100", "totalScore": "100", "backNum": 2, "isMarking": 1, "courseId": 3},
            {"id": 2, "examId": 12, "examName": "可重做", "state": 4,
             "score": "60", "totalScore": 100, "backNum": 2, "isMarking": 1, "courseId": 3},
            {"id": 3, "examId": 13, "examName": "次数用完", "state": 4,
             "score": 60, "totalScore": 100, "backNum": 2, "isMarking": 2, "courseId": 3},
        ]
        client.exam_rows = []
        by_id = {item["id"]: item for _, item, _ in catalog(client, COURSE)}
        self.assertEqual(by_id["shw-1-11"]["_unavailable"][0], "已满分")
        self.assertNotIn("_redo", by_id["shw-1-11"])

        redo = by_id["shw-2-12"]
        self.assertNotIn("_unavailable", redo)
        self.assertTrue(redo["_redo"])
        self.assertTrue(redo["zhs"]["redo"])
        self.assertIn("当前 60/100", redo["_hint"])
        self.assertIn("剩余重做 1 次", redo["_hint"])
        self.assertEqual((redo["frequency"], redo["answerCount"]), (2, 1))
        self.assertTrue(task_availability(redo, 1).available)

        self.assertEqual(by_id["shw-3-13"]["_unavailable"][0], "无重做次数")
        self.assertEqual((by_id["shw-3-13"]["frequency"], by_id["shw-3-13"]["answerCount"]),
                         (2, 0))

    def test_exam_list_skips_papers_already_listed_as_homework(self):
        client = self.make_client()
        client.homework_rows = [{"id": 1, "examId": 11, "examName": "第一章单元测试",
                                 "state": 4, "score": 8, "courseId": 3}]
        client.exam_rows = [{"id": "1", "examId": "11", "examName": "第一章单元测试", "state": 4},
                            {"id": 2, "examId": 22, "examName": "期末考试", "state": 4}]
        ids = [item["id"] for _, item, _ in catalog(client, COURSE)]
        self.assertEqual(ids, ["shw-1-11", "sex-2-22"])

    def test_homework_skips_bad_rows(self):
        client = self.make_client()
        client.homework_rows = [
            {"id": None, "examId": 1, "examName": "缺 id", "state": 1, "courseId": 3},
            {"id": 5, "examId": None, "examName": "缺 exam", "state": 1, "courseId": 3},
            {"id": 6, "examId": 7, "examName": "别的课", "state": 1, "courseId": 999},
        ]
        client.exam_rows = []
        self.assertEqual(catalog(client, COURSE), [])

    def test_exam_unavailable_reasons(self):
        rows = [
            {"id": 1, "examId": 11, "examName": "已交", "state": 4},
            {"id": 2, "examId": 12, "examName": "未开考", "state": 1, "faStudentExamRemainCount": 1},
            {"id": 3, "examId": 13, "examName": "没次数", "state": 2,
             "studentStartTime": "s", "faStudentExamRemainCount": 0},
            {"id": 4, "examId": 14, "examName": "可考", "state": 2,
             "studentStartTime": "s", "faStudentExamRemainCount": 2},
        ]
        client = self.make_client(exam_rows=rows)
        client.homework_rows = []
        by_id = {item["id"]: item for _, item, _ in catalog(client, COURSE)}
        self.assertEqual(by_id["sex-1-11"]["_unavailable"][0], "已提交")
        self.assertEqual(by_id["sex-1-11"]["_completion_status"], "submitted")
        # Not started, and no window given: Studia starts it with the picture code.
        self.assertNotIn("_unavailable", by_id["sex-2-12"])
        self.assertTrue(by_id["sex-2-12"]["_start"])
        self.assertTrue(by_id["sex-2-12"]["_waiting"])
        self.assertEqual(by_id["sex-3-13"]["_unavailable"][0], "无剩余次数")
        self.assertNotIn("_unavailable", by_id["sex-4-14"])
        self.assertTrue(task_availability(by_id["sex-4-14"], 2).available)
        # Every exam not yet handed in is entered with the platform's picture code.
        self.assertTrue(all(by_id[i].get("_captcha") for i in ("sex-2-12", "sex-3-13", "sex-4-14")))
        self.assertNotIn("_captcha", by_id["sex-1-11"])

    def test_answer_lock_reads_as_the_platform_does(self):
        # What the platform's own exam list does with getSaveAnswerLockResult before letting a student in:
        # 1 lets them in, 2 asks for an identity check, 3 says they are barred. The real exam came back 1.
        rows = [{"id": n, "examId": 10 + n, "examName": "考试%d" % n, "state": 2,
                 "studentStartTime": "2026-11-25 10:00:39", "faStudentExamRemainCount": 1} for n in (1, 2, 3, 4)]
        client = self.make_client(exam_rows=rows, lock={11: 1, 12: 2, 13: 3, 14: 0})
        client.homework_rows = []
        by_id = {item["id"]: item for _, item, _ in catalog(client, COURSE)}
        self.assertNotIn("_unavailable", by_id["sex-1-11"])
        self.assertNotIn("_waiting", by_id["sex-1-11"])
        self.assertEqual(by_id["sex-2-12"]["_unavailable"][0], "需要验证")
        self.assertTrue(by_id["sex-2-12"]["_waiting"])
        self.assertEqual(by_id["sex-3-13"]["_unavailable"][0], "禁止考试")
        self.assertFalse(by_id["sex-3-13"]["_waiting"])
        self.assertEqual(by_id["sex-4-14"]["_unavailable"][0], "状态未知")

    def test_an_exam_not_started_opens_for_starting_only_in_its_window(self):
        rows = [
            {"id": 1, "examId": 11, "examName": "下学期", "state": 1, "studentStartTime": None,
             "faStudentExamRemainCount": 1, "startTime": "2099-01-21 00:00:00", "endDate": "2099-01-31 23:59:59"},
            {"id": 2, "examId": 12, "examName": "本周", "state": 1, "studentStartTime": None,
             "faStudentExamRemainCount": 1, "startTime": "2026-01-01 00:00:00", "endDate": "2099-01-01 00:00:00",
             "parentId": None, "reviewType": 0},
            {"id": 3, "examId": 13, "examName": "过期", "state": 1, "studentStartTime": None,
             "faStudentExamRemainCount": 1, "startTime": "2020-01-01 00:00:00", "endDate": "2020-02-01 00:00:00"},
        ]
        client = self.make_client(exam_rows=rows)
        client.homework_rows = []
        by_id = {item["id"]: item for _, item, _ in catalog(client, COURSE)}
        self.assertEqual(task_availability(by_id["sex-1-11"], 2).label, "未开始")
        self.assertEqual(task_availability(by_id["sex-3-13"], 2).label, "已截止")
        open_now = by_id["sex-2-12"]
        self.assertTrue(task_availability(open_now, 2).available)
        self.assertTrue(open_now["_start"])
        self.assertIn("开考", open_now["_hint"])
        self.assertEqual(open_now["_entry"], {"start": True, "remain": 1, "parentId": None, "reviewType": 0})
        # Only the one that can be started now asks for its answer lock.
        self.assertEqual([p for n, p in client.calls if n == "shared_answer_lock"], [12])

    def test_answer_lock_failure_is_unknown(self):
        client = self.make_client()

        def down(exam_id, recruit_id):
            raise PlatformUnavailable("down")

        client.shared_answer_lock = down
        by_id = {item["id"]: item for _, item, _ in catalog(client, COURSE)}
        self.assertEqual(by_id["sex-300-400"]["_unavailable"][0], "状态未知")

    def test_submitted_final_exams_come_from_flag_two_with_scores(self):
        client = self.make_client()
        client.homework_rows = []
        by_flag = {
            1: [],
            2: [
                {"id": 10, "examId": 20, "examName": "期末考试", "state": 4, "score": 94},
                {"id": 11, "examId": 21, "examName": "期末补考", "state": 4, "parentId": 20, "oneHundredPont": 60, "score": 82},
                {"id": 12, "examId": 22, "examName": "待批阅考试", "state": 3, "score": ""},
            ],
        }
        client.shared_exam_list = lambda r, c, flag: [dict(x) for x in by_flag.get(flag, [])]
        by_id = {item["id"]: item for _, item, _ in catalog(client, COURSE)}
        self.assertEqual(by_id["sex-10-20"]["score"], 94)
        self.assertEqual(by_id["sex-10-20"]["_completion_status"], "submitted")
        self.assertEqual(by_id["sex-11-21"]["score"], 60)
        self.assertNotIn("score", by_id["sex-12-22"])
        self.assertEqual(by_id["sex-12-22"]["_completion_status"], "submitted")
        self.assertIn("等待平台公布成绩", by_id["sex-12-22"]["_unavailable"][1])

    def test_exam_submit_reports_score_when_platform_returns_one(self):
        client = FakeSharedClient([shared_question("e1")])
        client.shared_submit_exam = lambda *args: {"statu": 0, "score": 96, "totalScore": 100}
        result = runner(client, FakeAI(["B"])).run_paper(COURSE, exam_item(), 2)
        self.assertEqual(result["status"], "submitted")
        self.assertIn("96/100", result["message"])

    def test_exam_deduplicated(self):
        client = self.make_client()
        client.exam_rows = [{"id": 300, "examId": 400, "examName": "期末", "state": 2,
                             "studentStartTime": "s", "faStudentExamRemainCount": 3}]
        exams = [item for _, item, category in catalog(client, COURSE) if category == 2]
        self.assertEqual(len(exams), 1)

    def test_partial_and_total_failure(self):
        def fail_homework(*args):
            raise PlatformUnavailable("down")

        client = self.make_client()
        client.shared_homework_list = fail_homework
        entries = catalog(client, COURSE)
        self.assertEqual([category for _, _, category in entries], [2])

        client = self.make_client()
        client.shared_homework_list = fail_homework

        def fail_exam(*args):
            raise PlatformUnavailable("down")

        client.shared_exam_list = fail_exam
        with self.assertRaises(PlatformUnavailable):
            catalog(client, COURSE)

    def test_auth_error_propagates(self):
        client = self.make_client()

        def expired(*args):
            from core.auth import AuthenticationExpired
            raise AuthenticationExpired("expired")

        client.shared_homework_list = expired
        from core.auth import AuthenticationExpired
        with self.assertRaises(AuthenticationExpired):
            catalog(client, COURSE)


class UnavailableCapabilityTest(unittest.TestCase):
    def test_unavailable_item_is_not_selectable(self):
        item = {"_unavailable": ("已提交", "不自动重做")}
        availability = task_availability(item, 1)
        self.assertFalse(availability.available)
        self.assertEqual(availability.label, "已提交")
        self.assertEqual(availability.reason, "不自动重做")

    def test_attachment_still_wins(self):
        item = {"typeId": 3, "_unavailable": ("已提交", "不自动重做")}
        availability = task_availability(item, 1)
        self.assertEqual(availability.label, "暂不支持")


if __name__ == "__main__":
    unittest.main()
