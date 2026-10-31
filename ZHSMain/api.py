from __future__ import annotations

import base64
import json
import time
import urllib.parse

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

from MoocMain.log import Logger
from base.auth import AuthenticationExpired, PlatformUnavailable

logger = Logger(__name__).get_log()

IV = b"1g3qqdh4jvbskb9x"
KEYS = {"home": b"7q9oko0vqb3la20r", "video": b"azp53h0kft7qi78q", "ai": b"hw2fdlwcj4cs1mx7"}
EV_KEY = "zzpttjd"
BASE = "https://onlineservice-api.zhihuishu.com"
PASSPORT = "https://passport.zhihuishu.com"
STUDY = "https://studyservice-api.zhihuishu.com"
AI = "https://kg-ai-run.zhihuishu.com"
NEWBASE = "https://newbase.zhihuishu.com"

HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
    ),
    "Origin": "https://studyh5.zhihuishu.com",
    "Referer": "https://studyh5.zhihuishu.com/",
}

STUDY_GATEWAY = STUDY + "/gateway/t/v1"
AI_GATEWAY = AI + "/run/gateway/t/stu"


class ZHSError(RuntimeError):
    pass


class ZHSApiError(ZHSError):
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(f"智慧树接口返回 {code}：{message}")


class CaptchaRequired(ZHSError):
    pass


class StudyTimeLimit(ZHSError):
    pass


def encrypt(text, key):
    cipher = AES.new(key, AES.MODE_CBC, IV)
    data = pad(text.encode("utf-8"), AES.block_size)
    return base64.b64encode(cipher.encrypt(data)).decode("ascii")


def decrypt(text, key):
    cipher = AES.new(key, AES.MODE_CBC, IV)
    data = cipher.decrypt(base64.b64decode(text))
    return unpad(data, AES.block_size).decode("utf-8")


def encode_ev(values):
    text = ";".join(str(value) for value in values)
    parts = []
    for index, char in enumerate(text):
        mixed = ord(char) ^ ord(EV_KEY[index % len(EV_KEY)])
        parts.append(format(mixed, "02x")[-4:])
    return "".join(parts)


def _percent(value):
    """Course progress arrives as 58, "58.3" or "58.3%"; None when absent."""
    try:
        return round(float(str(value).strip().rstrip("%")))
    except (TypeError, ValueError):
        return None


class WatchPoints:
    def __init__(self, start=0):
        self.points = [0, 1]
        self.last = int(start) or 1

    def add(self, end):
        for point in range(self.last, int(end) + 1, 2):
            self.points.append(point // 5 + 2)
        self.last = int(end)

    def text(self):
        return ",".join(str(point) for point in self.points)

    def reset(self, start=0):
        self.__init__(start)


class ZHSApi:
    def __init__(self, access_token=None, token=None, username=None, password=None, session=None):
        self.session = session or requests.Session()
        self.session.headers.update(HEADERS)
        self.username = username
        self.password = password
        self.user_info = None
        saved = access_token or token
        if saved:
            self.load_cookies(saved)

    @property
    def access_token(self):
        cookies = [
            {"name": cookie.name, "value": cookie.value, "domain": cookie.domain, "path": cookie.path}
            for cookie in self.session.cookies
        ]
        return json.dumps(cookies, ensure_ascii=False) if cookies else ""

    def load_cookies(self, text):
        try:
            cookies = json.loads(text)
            for cookie in cookies:
                self.session.cookies.set(
                    cookie["name"],
                    cookie["value"],
                    domain=cookie.get("domain") or "",
                    path=cookie.get("path") or "/",
                )
        except (ValueError, TypeError, KeyError):
            raise AuthenticationExpired("保存的智慧树登录无效，请重新扫码") from None
        account = self.uuid
        if account:
            self.session.cookies.set("exitRecod_" + account, "2", domain="zhihuishu.com")

    @property
    def uuid(self):
        value = self.session.cookies.get("CASLOGC")
        if not value:
            return None
        try:
            return json.loads(urllib.parse.unquote(value)).get("uuid")
        except (ValueError, AttributeError):
            return None

    def close(self):
        self.session.close()

    def _request(self, method, url, *, params=None, data=None, json_body=None,
                 allow_redirects=True, expect_json=True):
        try:
            response = self.session.request(
                method,
                url,
                params=params,
                data=data,
                json=json_body,
                timeout=(10, 30),
                allow_redirects=allow_redirects,
            )
        except requests.RequestException:
            raise PlatformUnavailable("暂时无法连接智慧树，请稍后重试") from None
        if response.status_code in (401, 403):
            raise AuthenticationExpired("智慧树登录已过期，请重新扫码")
        if response.status_code >= 400:
            raise PlatformUnavailable(f"智慧树返回 HTTP {response.status_code}，请稍后重试")
        if not expect_json:
            return response
        try:
            result = response.json()
        except ValueError:
            raise PlatformUnavailable("智慧树响应无法解析，请稍后重试") from None
        if not isinstance(result, dict):
            raise PlatformUnavailable("智慧树返回了未知格式，请稍后重试")
        return result

    def secure(self, url, payload, *, key="video", ok=0, as_json=False, method="POST"):
        body = dict(payload or {})
        timestamp = int(time.time() * 1000)
        body["dateFormate"] = timestamp
        form = {
            "secretStr": encrypt(json.dumps(body), KEYS[key]),
            "dateFormate": str(timestamp),
        }
        if method.upper() == "GET":
            result = self._request("GET", url, params=form)
        elif as_json:
            result = self._request("POST", url, json_body=form)
        else:
            result = self._request("POST", url, data=form)

        code = result.get("code", ok)
        if code == -12:
            raise CaptchaRequired("智慧树要求验证码，请到网页完成验证后重试")
        if code != ok:
            raise ZHSApiError(code, result.get("message") or result.get("msg") or "")
        return result

    def login_qr(self):
        self._request(
            "GET",
            PASSPORT + "/login",
            params={"service": BASE + "/login/gologin"},
            expect_json=False,
        )
        result = self._request("GET", PASSPORT + "/qrCodeLogin/getLoginQrImg")
        if not result.get("qrToken") or not result.get("img"):
            raise ZHSError("二维码获取失败")
        return result["qrToken"], base64.b64decode(result["img"])

    def login_qr_status(self, qr_token):
        return self._request(
            "GET",
            PASSPORT + "/qrCodeLogin/getLoginQrInfo",
            params={"qrToken": qr_token},
        )

    def finish_qr_login(self, once_password):
        self._request(
            "GET",
            PASSPORT + "/login",
            params={"service": BASE + "/login/gologin", "pwd": once_password},
            allow_redirects=True,
            expect_json=False,
        )
        if len(self.session.cookies) == 0:
            raise ZHSError("登录后未获得 cookie")

    def shared_courses(self):
        url = BASE + "/gateway/t/v1/student/course/share/queryShareCourseInfo"
        courses = []
        total_pages = 1
        page = 1
        while page <= total_pages and page <= 200:
            result = self.secure(
                url,
                {"status": 0, "pageNo": page, "pageSize": 5},
                key="home",
                ok=200,
            )
            data = result.get("result")
            if not isinstance(data, dict) or not isinstance(data.get("courseOpenDtos"), list):
                raise PlatformUnavailable("智慧树课程列表返回格式异常，请稍后重试")
            if page == 1:
                try:
                    total = int(data.get("totalCount") or 0)
                except (TypeError, ValueError):
                    total = 0
                total_pages = max(1, (total + 4) // 5)
            courses.extend(data["courseOpenDtos"])
            page += 1
        return courses

    def ai_courses(self):
        result = self.secure(
            BASE + "/gateway/t/v1/student/queryStudentAICourseList",
            {"status": 3},
            key="home",
            ok=0,
        )
        courses = result.get("rt")
        if not isinstance(courses, list):
            raise PlatformUnavailable("智慧树课程列表返回格式异常，请稍后重试")
        return courses

    def my_course_list(self, page_size=9999, strict=False):
        rows = []
        failures = 0

        try:
            shared = self.shared_courses()
        except AuthenticationExpired:
            raise
        except Exception as exc:
            failures += 1
            logger.warning("读取智慧树共享课失败：%s", exc)
        else:
            for item in shared:
                row = self._shared_row(item)
                if row:
                    rows.append(row)

        try:
            ai_courses = self.ai_courses()
        except AuthenticationExpired:
            raise
        except Exception as exc:
            failures += 1
            logger.warning("读取智慧树智慧课程失败：%s", exc)
        else:
            for item in ai_courses:
                row = self._ai_row(item)
                if row:
                    rows.append(row)

        if failures >= 2:
            raise PlatformUnavailable("智慧树课程列表读取失败，请稍后重试")
        return {"rows": rows}

    def _shared_row(self, item):
        # The live list names the course key "secret"; older responses used recruitAndCourseId.
        secret = item.get("secret") or item.get("recruitAndCourseId")
        try:
            recruit_id = int(item.get("recruitId"))
        except (TypeError, ValueError):
            recruit_id = 0
        if not secret or recruit_id <= 0:
            logger.warning("跳过缺少共享课标识的课程：%s", item.get("courseName"))
            return None
        course_id = self._int_or_zero(item.get("courseId"))
        if course_id <= 0:
            course_info = item.get("courseInfo") or {}
            course_id = self._int_or_zero(course_info.get("courseId"))
        row = {
            "courseName": item.get("courseName") or "未命名课程",
            "courseInfoName": "共享课",
            "zhs": {
                "kind": "shared",
                "secret": secret,
                "recruitId": recruit_id,
                "courseId": course_id,
            },
        }
        progress = _percent(item.get("progress"))
        if progress is not None:
            row["studySpeed"] = progress
        return row

    def _ai_row(self, item):
        course_id = self._int_or_zero(item.get("courseId"))
        class_id = self._int_or_zero(item.get("classId"))
        if course_id <= 0 or class_id <= 0:
            return None
        row = {
            "courseName": item.get("courseName") or "未命名课程",
            "courseInfoName": "智慧课程",
            "zhs": {"kind": "ai", "courseId": course_id, "classId": class_id},
        }
        progress = _percent(item.get("schedule"))
        if progress is not None:
            row["studySpeed"] = progress
        return row

    @staticmethod
    def _int_or_zero(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def shared_gologin(self, secret):
        return self._request(
            "GET",
            STUDY + "/login/gologin",
            params={
                "fromurl": "https://studyh5.zhihuishu.com/videoStudy.html#/studyVideo?recruitAndCourseId="
                + secret
            },
            expect_json=False,
        )

    def shared_course(self, secret):
        return self.secure(STUDY_GATEWAY + "/learning/queryCourse", {"recruitAndCourseId": secret})["data"]

    def shared_videos(self, secret):
        return self.secure(STUDY_GATEWAY + "/learning/videolist", {"recruitAndCourseId": secret})["data"]

    def shared_study_info(self, lesson_ids, video_ids, recruit_id):
        return self.secure(
            STUDY_GATEWAY + "/learning/queryStuyInfo",
            {"lessonIds": lesson_ids, "lessonVideoIds": video_ids, "recruitId": recruit_id},
        )["data"]

    def shared_last_video(self, recruit_id):
        try:
            return self.secure(
                STUDY_GATEWAY + "/learning/queryUserRecruitIdLastVideoId",
                {"recruitId": recruit_id},
            )
        except (AuthenticationExpired, CaptchaRequired):
            raise
        except Exception as exc:
            logger.debug("读取上次观看视频失败：%s", exc)
            return None

    def shared_prelearning(self, payload):
        return self.secure(STUDY_GATEWAY + "/learning/prelearningNote", payload)["data"]

    def shared_question_points(self, payload):
        return self.secure(STUDY_GATEWAY + "/popupAnswer/loadVideoPointerInfo", payload)["data"]

    def shared_popup_question(self, payload):
        return self.secure(STUDY_GATEWAY + "/popupAnswer/lessonPopupExam", payload)["data"]

    def shared_save_popup(self, payload):
        return self.secure(STUDY_GATEWAY + "/popupAnswer/saveLessonPopupExamSaveAnswer", payload)

    def shared_courseware(self, video_id):
        try:
            return self.secure(
                STUDY_GATEWAY + "/course/threeDimensionalCourseWare",
                {"videoId": video_id},
                method="GET",
            )
        except (AuthenticationExpired, CaptchaRequired):
            raise
        except Exception as exc:
            logger.debug("读取课件信息失败：%s", exc)
            return None

    def shared_save_cache(self, payload):
        try:
            return self.secure(STUDY_GATEWAY + "/learning/saveCacheIntervalTimeV2", payload)
        except (AuthenticationExpired, CaptchaRequired):
            raise
        except Exception as exc:
            logger.debug("保存缓存进度失败：%s", exc)
            return None

    def shared_save_progress(self, payload):
        return self.secure(STUDY_GATEWAY + "/learning/saveDatabaseIntervalTimeV2", payload)

    def ai_course_basic(self, course_id, class_id):
        return self.secure(
            AI_GATEWAY + "/knowledge-study/course-basic",
            {"courseId": course_id, "classId": class_id},
            key="ai",
            ok=200,
            as_json=True,
        )["data"]

    def ai_resources(self, course_id, class_id, knowledge_id):
        data = self.secure(
            AI_GATEWAY + "/resources/list-knowledge-resource",
            {"courseId": course_id, "classId": class_id, "knowledgeId": knowledge_id},
            key="ai",
            ok=200,
            as_json=True,
        )["data"]
        resources = data.get("resourceList") if isinstance(data, dict) else None
        if not isinstance(resources, list):
            raise PlatformUnavailable("智慧树课程资源返回格式异常，请稍后重试")
        return resources

    def ai_complete(self, course_id, class_id, knowledge_id, resources_uid):
        return self.secure(
            AI_GATEWAY + "/studyRecord/completed",
            {
                "courseId": course_id,
                "classId": class_id,
                "knowledgeId": knowledge_id,
                "resourcesUid": resources_uid,
                "watchUId": 1,
            },
            key="ai",
            ok=200,
            as_json=True,
        )

    def ai_video_length(self, course_id, class_id, file_id):
        data = self.secure(
            AI_GATEWAY + "/resources-lab/get-video-time",
            {"courseId": course_id, "classId": class_id, "videoIdList": [file_id]},
            key="ai",
            ok=200,
            as_json=True,
        )["data"]
        return int(data[0]["time"])

    def ai_report(self, course_id, class_id, file_id, knowledge_id, position):
        return self.secure(
            AI_GATEWAY + "/studyRecord/report",
            {
                "courseId": course_id,
                "classId": class_id,
                "fileId": file_id,
                "knowledgeId": knowledge_id,
                "lastWatchTime": position,
                "studyTotalTime": 10,
                "shareCourseId": "",
                "nodeType": 0,
                "watchUId": 1,
            },
            key="ai",
            ok=200,
            as_json=True,
        )

    def open_video(self, video_id=None, file_id=None):
        try:
            if video_id:
                response = requests.get(
                    NEWBASE + "/video/initVideo",
                    params={
                        "jsonpCallBack": "result",
                        "videoID": str(video_id),
                        "_": int(time.time() * 1000),
                    },
                    headers=HEADERS,
                    timeout=(10, 30),
                )
                text = response.text
                start = text.find("(")
                end = text.rfind(")")
                if start < 0 or end <= start:
                    return
                data = json.loads(text[start + 1:end])
                lines = (data.get("result") or {}).get("lines") or []
                line_url = lines[0].get("lineUrl") if lines else None
                if not line_url:
                    return
                with requests.get(line_url, headers=HEADERS, stream=True, timeout=(10, 30)) as stream:
                    stream.raw.read(64 * 1024)
            elif file_id:
                requests.get(
                    NEWBASE + "/video/initVideo",
                    params={"fileId": file_id},
                    headers=HEADERS,
                    timeout=(10, 30),
                )
        except Exception as exc:
            logger.debug("视频流预请求失败：%s", exc)
