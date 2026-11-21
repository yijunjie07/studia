"""职教云 now and then answers a read with code 500 and the same read goes through a moment later.
List reads are asked again; a read that still fails is an error, never an empty course or paper list."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests

from core.auth import AuthenticationExpired, PlatformUnavailable
from mooc.api import AIMoocApi
from mooc.exam_api import ExamAPI, ExamError
from mooc.main import course_units

HICCUP = {"code": 500, "msg": "内部服务器错误"}


def reply(payload, status=200):
    response = Mock(status_code=status)
    response.json.return_value = payload
    return response


def exam_api(*replies):
    session = Mock()
    session.headers = {}
    session.request.side_effect = list(replies)
    client = SimpleNamespace(user_id="u1", default_base_url="https://example.invalid/prod-api", access_token="t")
    return ExamAPI(client, session), session


def mooc_api(*replies):
    api = object.__new__(AIMoocApi)
    api.session = Mock()
    api.session.get.side_effect = list(replies)
    api.default_base_url = "https://example.invalid/prod-api"
    return api


@patch("mooc.exam_api.time.sleep")
class ExamListTests(unittest.TestCase):
    def test_paper_list_is_read_again_after_a_code_500(self, sleep):
        api, session = exam_api(reply(HICCUP), reply({"code": 200, "rows": [{"id": "e1", "name": "第一次作业"}]}))
        self.assertEqual([x["id"] for x in api.catalog({"id": "i", "courseId": "c"}, 1)], ["e1"])
        self.assertEqual(session.request.call_count, 2)
        sleep.assert_called_once()

    def test_paper_list_that_keeps_failing_says_so_without_blaming_opening_times(self, sleep):
        api, session = exam_api(reply(HICCUP), reply(HICCUP), requests.ConnectionError("x"))
        with self.assertRaises(ExamError) as raised:
            api.catalog({"id": "i", "courseId": "c"}, 2)
        self.assertEqual(session.request.call_count, 3)
        message = str(raised.exception)
        self.assertIn("试卷列表没读到", message)
        self.assertIn("连读 3 次", message)
        self.assertNotIn("开放时间", message)

    def test_a_refusal_other_than_500_is_not_asked_again(self, sleep):
        api, session = exam_api(reply({"code": 205, "msg": "无权限"}))
        with self.assertRaises(ExamError) as raised:
            api.catalog({"id": "i", "courseId": "c"}, 1)
        self.assertEqual(session.request.call_count, 1)
        self.assertIn("code=205（无权限）", str(raised.exception))
        sleep.assert_not_called()

    def test_writes_are_never_repeated(self, sleep):
        api, session = exam_api(reply(HICCUP))
        with self.assertRaises(ExamError) as raised:
            api.submit({})
        self.assertEqual(session.request.call_count, 1)
        self.assertIn("内部服务器错误", str(raised.exception))
        sleep.assert_not_called()


@patch("mooc.api.time.sleep")
class UnitListTests(unittest.TestCase):
    def test_chapter_list_is_read_again_after_a_code_500(self, sleep):
        api = mooc_api(reply(HICCUP), reply({"code": 200, "data": [{"id": "c1"}]}))
        self.assertEqual(api.study_design_list("i", "c"), [{"id": "c1"}])
        self.assertEqual(api.session.get.call_count, 2)

    def test_a_read_that_keeps_failing_raises_instead_of_reading_empty(self, sleep):
        api = mooc_api(reply(HICCUP), reply({}, status=502), requests.Timeout("x"))
        with self.assertRaises(PlatformUnavailable) as raised:
            api.get_cell_list("i", "c", "p")
        self.assertEqual(api.session.get.call_count, 3)
        self.assertIn("章节资源没读到", str(raised.exception))

    def test_expired_login_and_odd_shapes_are_not_asked_again(self, sleep):
        with self.assertRaises(AuthenticationExpired):
            mooc_api(reply({"code": 401, "msg": "令牌不能为空"})).study_record_list("i", "c")
        api = mooc_api(reply({"code": 200, "data": {"rows": []}}))
        with self.assertRaises(PlatformUnavailable):
            api.study_record_list("i", "c")
        self.assertEqual(api.session.get.call_count, 1)
        sleep.assert_not_called()

    def test_an_empty_answer_is_an_empty_list(self, sleep):
        self.assertEqual(mooc_api(reply({"code": 200, "data": None})).study_design_list("i", "c"), [])

    def test_course_grid_fails_when_a_chapter_cannot_be_read(self, sleep):
        api = mooc_api()
        lists = {"/course/studyRecord/completed/courseware": {"code": 200, "data": []},
                 "/course/courseDesign/getStudentDesignList": {"code": 200, "data": [{"id": "c1", "name": "第一章"}]},
                 "/course/courseDesign/getCellList": HICCUP}
        api.session.get.side_effect = lambda url, **kwargs: reply(lists[url.removeprefix(api.default_base_url)])
        with self.assertRaises(PlatformUnavailable):
            course_units(api, {"id": "i", "courseId": "c"})


class UnitsPageTests(unittest.TestCase):
    def test_a_failed_unit_read_is_not_kept_and_the_next_visit_reads_again(self):
        import tempfile
        from core.settings import SettingsStore
        from web.server import Studia
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        app = Studia(SettingsStore(directory.name), oauth=Mock(return_value=None))
        platform = app.platforms["mooc"]
        platform.rows, platform.client = [{"courseId": "c1", "id": "i1"}], Mock()
        answers = [PlatformUnavailable("章节目录没读到"), [{"name": "第一章", "units": []}]]

        def units(client, row):
            answer = answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer
        platform.spec = dict(platform.spec, units=units)
        with self.assertRaises(PlatformUnavailable):
            app.units("mooc", "c1")
        self.assertEqual(app.units("mooc", "c1")["chapters"][0]["name"], "第一章")


if __name__ == "__main__":
    unittest.main()
