import json
import unittest
import urllib.parse
from unittest.mock import Mock, patch

from base.auth import AuthenticationExpired, PlatformUnavailable
from ZHSMain import api
from ZHSMain.api import (
    CaptchaRequired,
    KEYS,
    WatchPoints,
    ZHSApi,
    ZHSApiError,
    ZHSError,
    decrypt,
    encode_ev,
    encrypt,
)


def make_api():
    session = Mock()
    session.cookies = __import__("requests").cookies.RequestsCookieJar()
    session.request = Mock()
    session.headers = {}
    return ZHSApi(session=session)


def json_response(payload, status=200):
    response = Mock()
    response.status_code = status
    response.json.return_value = payload
    return response


class CryptoTest(unittest.TestCase):
    def test_encrypt_matches_platform(self):
        self.assertEqual(
            encrypt('{"recruitAndCourseId": "abc", "dateFormate": 1700000000000}', KEYS["video"]),
            "QhSgx0MEvvp0jRL20aaxWlqKuqDVmx7L/zSqUDNH1p0IgiNl5O4aghZhx93U7vK6sAmahUAv75/UtGVSZlqWDg==",
        )
        cipher = encrypt('{"name": "中文"}', KEYS["ai"])
        self.assertEqual(cipher, "Nx637e4NA8F2H8efwRHDPK+YUeeM2Xkhkj9YVbkb4AA=")
        self.assertEqual(decrypt(cipher, KEYS["ai"]), '{"name": "中文"}')

    def test_encode_ev(self):
        self.assertEqual(
            encode_ev([123, 45, 6, 789, 10, "0", 30, 95, "0:01:35", "abc-uuidzhs"]),
            "4b48434f405f5f4c41474c4d51554a41404f475a5f434f4b444e5a554049454f150807570f051d10100c09",
        )
        self.assertEqual(encode_ev([1, "0:00:00", "x"]), "4b41404e445a5e4a4a4b0c")

    def test_watch_points(self):
        points = WatchPoints()
        points.add(10)
        points.add(17)
        self.assertEqual(points.text(), "0,1,2,2,3,3,3,4,4,4,5")
        points.reset(40)
        points.add(45)
        self.assertEqual(points.text(), "0,1,10,10,10")


class SecureTest(unittest.TestCase):
    def test_form_post_and_decrypt_body(self):
        client = make_api()
        client.session.request.return_value = json_response({"code": 0, "data": {"ok": 1}})
        result = client.secure("https://x.test/path", {"a": 1})
        self.assertEqual(result["data"], {"ok": 1})
        _, kwargs = client.session.request.call_args
        self.assertIn("secretStr", kwargs["data"])
        self.assertIsNone(kwargs["json"])
        body = json.loads(decrypt(kwargs["data"]["secretStr"], KEYS["video"]))
        self.assertEqual(body["a"], 1)
        self.assertIn("dateFormate", body)

    def test_json_post(self):
        client = make_api()
        client.session.request.return_value = json_response({"code": 200})
        client.secure("https://x.test/path", {"a": 1}, key="ai", ok=200, as_json=True)
        _, kwargs = client.session.request.call_args
        self.assertIn("secretStr", kwargs["json"])
        self.assertIn("json", kwargs)

    def test_captcha_and_api_error(self):
        client = make_api()
        client.session.request.return_value = json_response({"code": -12})
        with self.assertRaises(CaptchaRequired):
            client.secure("https://x.test/path", {})
        client.session.request.return_value = json_response({"code": 5, "msg": "boom"})
        with self.assertRaises(ZHSApiError) as ctx:
            client.secure("https://x.test/path", {})
        self.assertEqual(ctx.exception.code, 5)
        self.assertIn("boom", str(ctx.exception))

    def test_missing_code_is_success(self):
        client = make_api()
        client.session.request.return_value = json_response({"data": 1})
        self.assertEqual(client.secure("https://x.test/path", {}), {"data": 1})

    def test_unauthorized(self):
        client = make_api()
        client.session.request.return_value = json_response({}, status=401)
        with self.assertRaises(AuthenticationExpired):
            client.secure("https://x.test/path", {})


class CookieTest(unittest.TestCase):
    def test_access_token_roundtrip(self):
        client = make_api()
        saved = json.dumps([
            {"name": "CASLOGC", "value": "abc", "domain": ".zhihuishu.com", "path": "/"}
        ])
        client.load_cookies(saved)
        self.assertEqual(json.loads(client.access_token), json.loads(saved))

    def test_uuid_and_exit_record(self):
        client = make_api()
        raw = json.dumps({"uuid": "user-1"})
        client.load_cookies(json.dumps([
            {"name": "CASLOGC", "value": urllib.parse.quote(raw), "domain": ".zhihuishu.com", "path": "/"}
        ]))
        self.assertEqual(client.uuid, "user-1")
        self.assertEqual(client.session.cookies.get("exitRecod_user-1"), "2")

    def test_invalid_cookies(self):
        client = make_api()
        with self.assertRaises(AuthenticationExpired):
            client.load_cookies("not-json")

    def test_empty_access_token(self):
        self.assertEqual(make_api().access_token, "")


class CourseListTest(unittest.TestCase):
    def test_shared_courses_pagination(self):
        client = make_api()
        pages = {
            1: {"code": 200, "result": {"totalCount": 7, "courseOpenDtos": [{"id": 1}]}},
            2: {"code": 200, "result": {"totalCount": 7, "courseOpenDtos": [{"id": 2}]}},
        }
        calls = []

        def request(method, url, **kwargs):
            body = json.loads(decrypt(kwargs["data"]["secretStr"], KEYS["home"]))
            calls.append(body["pageNo"])
            return json_response(pages[body["pageNo"]])

        client.session.request.side_effect = request
        self.assertEqual(client.shared_courses(), [{"id": 1}, {"id": 2}])
        self.assertEqual(calls, [1, 2])

    def test_my_course_list_rows(self):
        client = make_api()
        client.shared_courses = Mock(return_value=[
            {"recruitAndCourseId": "s1", "courseName": "共享", "recruitId": "9",
             "courseId": 0, "courseInfo": {"courseId": 3}, "progress": 12.6},
            {"courseName": "坏数据", "recruitId": "0"},
        ])
        client.ai_courses = Mock(return_value=[
            {"courseName": "", "courseId": "7", "classId": "8"},
            {"courseName": "坏", "courseId": "x", "classId": 1},
        ])
        rows = client.my_course_list()["rows"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["courseInfoName"], "共享课")
        self.assertEqual(rows[0]["zhs"], {"kind": "shared", "secret": "s1", "recruitId": 9, "courseId": 3})
        self.assertEqual(rows[0]["studySpeed"], 13)
        self.assertEqual(rows[1]["courseName"], "未命名课程")
        self.assertEqual(rows[1]["zhs"], {"kind": "ai", "courseId": 7, "classId": 8})

    def test_one_side_failure(self):
        client = make_api()
        client.shared_courses = Mock(side_effect=PlatformUnavailable("down"))
        client.ai_courses = Mock(return_value=[{"courseName": "AI", "courseId": 1, "classId": 2}])
        self.assertEqual(len(client.my_course_list()["rows"]), 1)

    def test_both_side_failure(self):
        client = make_api()
        client.shared_courses = Mock(side_effect=PlatformUnavailable("down"))
        client.ai_courses = Mock(side_effect=PlatformUnavailable("down"))
        with self.assertRaises(PlatformUnavailable):
            client.my_course_list()

    def test_auth_error_propagates(self):
        client = make_api()
        client.shared_courses = Mock(side_effect=AuthenticationExpired("expired"))
        client.ai_courses = Mock(return_value=[])
        with self.assertRaises(AuthenticationExpired):
            client.my_course_list()


class LoginTest(unittest.TestCase):
    def test_login_qr(self):
        client = make_api()
        client.session.request.side_effect = [
            json_response({}),
            json_response({"qrToken": "qt", "img": "aGk="}),
        ]
        token, image = client.login_qr()
        self.assertEqual(token, "qt")
        self.assertEqual(image, b"hi")
        first, second = client.session.request.call_args_list
        self.assertTrue(first.args[1].endswith("/login"))
        self.assertEqual(first.kwargs["params"]["service"], api.BASE + "/login/gologin")
        self.assertTrue(second.args[1].endswith("/qrCodeLogin/getLoginQrImg"))

    def test_login_qr_status(self):
        client = make_api()
        client.session.request.return_value = json_response({"status": 0})
        self.assertEqual(client.login_qr_status("qt")["status"], 0)
        _, kwargs = client.session.request.call_args
        self.assertEqual(kwargs["params"], {"qrToken": "qt"})

    def test_finish_qr_login(self):
        client = make_api()
        client.session.request.return_value = json_response({})
        client.session.cookies.set("CASLOGC", "abc", domain=".zhihuishu.com", path="/")
        client.finish_qr_login("once")
        _, kwargs = client.session.request.call_args
        self.assertEqual(kwargs["params"], {"service": api.BASE + "/login/gologin", "pwd": "once"})
        self.assertTrue(kwargs["allow_redirects"])
        client.session.cookies.clear()
        with self.assertRaises(ZHSError):
            client.finish_qr_login("once")


if __name__ == "__main__":
    unittest.main()
