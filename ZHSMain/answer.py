"""智慧课程 AI 答题：知识点作业与考试。"""
from __future__ import annotations

import random
import re
import threading
import time

from AIMoocMain.export_questions import clean_html_text
from ai.client import AIError, AITransientServiceError
from base.auth import AuthenticationExpired, PlatformUnavailable
from MoocMain.log import Logger
from reporting import Reporter
from ZHSMain.api import CaptchaRequired, StudyTimeLimit

logger = Logger(__name__).get_log()

JOIN = "#@#"
FILL_HOMEWORK = "#@#"
FILL_EXAM = "/"
OPTION_TYPES = {1, 2, 14}
MEDIA = re.compile(r"<(img|audio|video|iframe)\b", re.I)


def _kind(raw):
    try:
        return int(raw.get("questionType"))
    except (TypeError, ValueError):
        raise ValueError("暂不支持该题型") from None


def _text(raw):
    value = raw.get("content") or ""
    if MEDIA.search(str(value)):
        raise ValueError("包含图片或音视频，需要人工处理")
    return clean_html_text(value)


def prepare(raw):
    """Turn a platform question into the public AI payload plus answer mappings."""
    if not isinstance(raw, dict):
        raise ValueError("题目数据格式异常")
    kind = _kind(raw)
    if kind not in OPTION_TYPES and kind != 3:
        raise ValueError("暂不支持该题型")
    title = _text(raw)
    if not title:
        raise ValueError("题干为空")
    options = [option for option in (raw.get("optionVos") or []) if isinstance(option, dict)]
    ids = {}
    public = {"title": title}
    if kind == 3:
        blank_count = max(1, len(options))
        public.update({"type": "填空题", "blank_count": blank_count})
        return {"qid": raw.get("id"), "kind": kind, "public": public,
                "ids": ids, "blank_count": blank_count}

    if len(options) < 2:
        raise ValueError("题目选项不足")
    texts = []
    for index, option in enumerate(options):
        label = chr(ord("A") + index)
        if option.get("id") in (None, ""):
            raise ValueError("选项缺少平台 ID")
        ids[label] = option.get("id")
        texts.append({"label": label, "text": _text(option)})
    public["type"] = "多选题" if kind == 2 else "单选题"
    public["options"] = texts
    return {"qid": raw.get("id"), "kind": kind, "public": public,
            "ids": ids, "blank_count": 0}


def encode(prepared, answer, *, fill_sep):
    """Map the model answer back to platform option ids or blank text."""
    invalid = ValueError("AI 返回的答案格式不符")
    kind = prepared["kind"]
    ids = prepared["ids"]
    if kind in (1, 14):
        if not isinstance(answer, str) or answer not in ids:
            raise invalid
        return [ids[answer]]
    if kind == 2:
        if (not isinstance(answer, list) or not answer
                or any(not isinstance(label, str) or label not in ids for label in answer)
                or len(set(answer)) != len(answer)):
            raise invalid
        return [ids[label] for label in answer]
    if kind == 3:
        blanks = [answer] if isinstance(answer, str) else answer
        if (not isinstance(blanks, list) or len(blanks) != prepared["blank_count"]
                or any(not isinstance(text, str) or not text.strip() for text in blanks)):
            raise invalid
        return [fill_sep.join(text.strip() for text in blanks)]
    raise invalid


def _positive_int(value):
    if isinstance(value, bool):
        return 0
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


class ZHSAnswerRunner:
    def __init__(self, client, ai_client, *, auto_submit, on_progress=None, sleep=time.sleep,
                 rng=None, heartbeat_interval=10, batch_size=5, cancel_event=None):
        self.client = client
        self.ai_client = ai_client
        self.auto_submit = auto_submit
        self.reporter = Reporter(on_progress)
        self.sleep = sleep
        self.rng = rng or random.Random()
        self.heartbeat_interval = heartbeat_interval
        self.batch_size = max(1, int(batch_size))
        self.cancel_event = cancel_event if cancel_event is not None else threading.Event()
        self._heartbeat_stop = None
        self._heartbeat_thread = None
        self._heartbeat_error = None

    # ------------------------------------------------------------------ 入口

    def run_paper(self, course, item, category):
        z = item.get("zhs") or {}
        cz = course.get("zhs") or {}
        name = item.get("name") or "未命名试卷"
        kind = z.get("kind")
        try:
            if kind == "ai_homework":
                return self._homework(z, cz, name)
            if kind == "ai_exam":
                return self._exam(z, cz, name)
        except KeyError as exc:
            return self._result(name, "error", "试卷缺少必要字段：%s" % exc)
        except (CaptchaRequired, StudyTimeLimit, AuthenticationExpired, KeyboardInterrupt):
            raise
        except Exception as exc:
            # Opening the paper or reading its sheet failed: nothing was saved, so
            # this paper fails alone and the queue can continue.
            return self._result(name, "error", "打开试卷失败：%s" % exc)
        return self._result(name, "error", "不支持的智慧树试卷类型")

    def _homework(self, z, cz, name):
        course_id = z.get("courseId", cz.get("courseId"))
        knowledge_id = z["knowledgeId"]
        test_id = int(z["examTestId"])
        paper_id = int(z["paperId"])
        self.client.exam_open({
            "examTestId": test_id,
            "examPaperId": paper_id,
            "courseId": course_id,
        })
        sheet = self.client.exam_sheet(test_id, paper_id, all_parts=False)

        def save_one(entry, prepared, encoded):
            self.client.exam_save_answer({
                "recruitId": course_id,
                "examTestId": test_id,
                "examPaperId": paper_id,
                "questionId": entry["questionId"],
                "dataVos": None,
                "answer": JOIN.join(str(part) for part in encoded),
            })

        def submit():
            self.client.exam_submit({
                "examTestId": test_id,
                "courseId": course_id,
                "courseType": 8,
                "examPaperId": paper_id,
                "aiKnlowledgeId": knowledge_id,
            })

        def after_submit():
            correct = self._count_correct(test_id, paper_id, sheet)
            return {"paper": name, "status": "submitted", "correct": correct,
                    "total": len(sheet), "message": "答对 %d/%d 题" % (correct, len(sheet))}

        return self._run(name, test_id, paper_id, sheet, fill_sep=FILL_HOMEWORK,
                         save_one=save_one, submit=submit, after_submit=after_submit)

    def _exam(self, z, cz, name):
        course_id = z.get("courseId", cz.get("courseId"))
        class_id = z.get("classId", cz.get("classId"))
        test_id = int(z["examTestId"])
        paper_id = int(z["examPaperId"])
        task_id = z.get("taskId")
        user_id = z.get("userId")
        self.client.ai_exam_pull_paper(course_id, class_id, test_id)
        self.client.exam_open({"examTestId": test_id, "courseId": course_id})
        sheet = self.client.exam_sheet(test_id, paper_id, all_parts=True)

        def item_of(entry, prepared, encoded):
            return {
                "recruitId": course_id,
                "examTestId": test_id,
                "examPaperId": paper_id,
                "questionId": entry["questionId"],
                "answer": JOIN.join(str(part) for part in encoded),
                "questionType": prepared["kind"],
                "dataVos": None,
            }

        def flush(batch):
            self.client.exam_save_batch({
                "examTestId": test_id,
                "examPaperId": paper_id,
                "recruitId": course_id,
                "answerList": batch,
            })

        def submit():
            self.client.exam_submit(
                {"examTestId": test_id, "recruitId": course_id, "examPaperId": paper_id},
                expect_body=False,
            )

        def after_submit():
            try:
                detail = self.client.ai_exam_detail({
                    "classId": class_id,
                    "courseId": course_id,
                    "examTestId": test_id,
                    "examPaperId": paper_id,
                    "examId": paper_id,
                    "studentId": user_id,
                    "taskId": task_id,
                    "taskType": None,
                })
            except (CaptchaRequired, StudyTimeLimit, AuthenticationExpired, KeyboardInterrupt):
                raise
            except Exception as exc:
                logger.warning("%s：读取考试详情失败：%s", name, exc)
                detail = {}
            if detail.get("isLookAnswer") == 1 or detail.get("isAllowShowDetail") == 1:
                correct = self._count_correct(test_id, paper_id, sheet)
                return {"paper": name, "status": "submitted", "correct": correct,
                        "total": len(sheet),
                        "message": "答对 %d/%d 题" % (correct, len(sheet))}
            return {"paper": name, "status": "submitted",
                    "message": "已交卷；平台未开放答案，成绩以平台为准"}

        return self._run(name, test_id, paper_id, sheet, fill_sep=FILL_EXAM,
                         save_one=None, item_of=item_of, flush=flush,
                         submit=submit, after_submit=after_submit)

    # ------------------------------------------------------------------ 流程

    def _run(self, name, test_id, paper_id, sheet, *, fill_sep, save_one=None,
             item_of=None, flush=None, submit=None, after_submit=None):
        if not isinstance(sheet, list):
            return self._result(name, "error", "答题卡格式异常")
        total = len(sheet)
        if total == 0:
            return self._result(name, "error", "答题卡为空")
        self.reporter.questions(name, 0, total)
        self._start_heartbeat(test_id, paper_id)
        try:
            batch = []
            for index, entry in enumerate(sheet, 1):
                if self.cancel_event.is_set():
                    raise KeyboardInterrupt
                self._raise_heartbeat_error()
                self.reporter.detail("%s · 第 %d/%d 题" % (name, index, total))
                self.sleep(self.rng.uniform(3, 5))
                try:
                    raw = self.client.exam_question(
                        test_id, paper_id, entry["questionId"], entry["version"])
                    prepared = prepare(raw)
                    reply = self._ask(prepared["public"])
                    encoded = encode(prepared, reply.get("answer"), fill_sep=fill_sep)
                except (CaptchaRequired, StudyTimeLimit, AuthenticationExpired, KeyboardInterrupt):
                    raise
                except AIError as exc:
                    return self._result(name, "ai_error", "第 %d 题：%s" % (index, exc))
                except Exception as exc:
                    return self._result(name, "error", "第 %d 题：%s" % (index, exc))
                try:
                    if save_one is not None:
                        save_one(entry, prepared, encoded)
                    else:
                        batch.append(item_of(entry, prepared, encoded))
                        if len(batch) >= self.batch_size:
                            flush(batch)
                            batch = []
                except (CaptchaRequired, StudyTimeLimit, AuthenticationExpired, KeyboardInterrupt):
                    raise
                except Exception as exc:
                    return self._result(name, "error", "第 %d 题保存失败：%s" % (index, exc))
                self.reporter.questions(name, index, total)
            if batch:
                try:
                    flush(batch)
                except (CaptchaRequired, StudyTimeLimit, AuthenticationExpired, KeyboardInterrupt):
                    raise
                except Exception as exc:
                    return self._result(name, "error", "保存答案失败：%s" % exc)
            if not self.auto_submit:
                return self._result(name, "preview", "答案已保存，未交卷")
            try:
                submit()
            except (CaptchaRequired, StudyTimeLimit, AuthenticationExpired, KeyboardInterrupt):
                raise
            except Exception:
                # Never resubmit: a duplicate attempt is worse than an unknown result.
                self.reporter.detail("%s · 提交请求失败" % name)
                return self._result(name, "submission_unknown",
                                    "提交结果未知，请到平台核对；未重试")
            return after_submit()
        finally:
            self._stop_heartbeat()

    def _ask(self, public):
        attempts = 0
        while True:
            try:
                reply = self.ai_client.answer(public)
            except AITransientServiceError:
                if attempts >= 2:
                    raise
                attempts += 1
                self.sleep(2)
                continue
            if not isinstance(reply, dict):
                raise ValueError("AI 返回的答案格式不符")
            return reply

    def _count_correct(self, test_id, paper_id, sheet):
        correct = 0
        for entry in sheet:
            try:
                raw = self.client.exam_question(
                    test_id, paper_id, entry["questionId"], entry["version"])
            except (CaptchaRequired, StudyTimeLimit, AuthenticationExpired, KeyboardInterrupt):
                raise
            except Exception as exc:
                logger.warning("回查第 %s 题失败：%s", entry.get("questionId"), exc)
                continue
            answers = (raw or {}).get("userAnswerVo") or []
            if answers and isinstance(answers[0], dict) and answers[0].get("isCorrect") == 1:
                correct += 1
        return correct

    def _result(self, name, status, message):
        result = {"paper": name, "status": status, "message": message}
        if status not in ("submitted", "preview"):
            logger.warning("%s：%s（%s）", name, message, status)
        return result

    # ---------------------------------------------------------------- 心跳

    def _start_heartbeat(self, test_id, paper_id):
        self._heartbeat_stop = threading.Event()
        self._heartbeat_error = None
        interval = self.heartbeat_interval

        def beat():
            while not self._heartbeat_stop.wait(interval):
                try:
                    self.client.exam_heartbeat(test_id, paper_id, interval)
                except (CaptchaRequired, AuthenticationExpired) as exc:
                    self._heartbeat_error = exc
                    return
                except Exception:
                    continue

        self._heartbeat_thread = threading.Thread(target=beat, daemon=True)
        self._heartbeat_thread.start()

    def _stop_heartbeat(self):
        if self._heartbeat_stop is not None:
            self._heartbeat_stop.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=5)
        self._heartbeat_stop = None
        self._heartbeat_thread = None

    def _raise_heartbeat_error(self):
        error = self._heartbeat_error
        if error is not None:
            self._heartbeat_error = None
            raise error


# -------------------------------------------------------------------- 目录

def _knowledge_points(basic):
    points = []
    for theme in (basic or {}).get("cakeThemeList") or []:
        if isinstance(theme, dict):
            points.extend(theme.get("knowledgeList") or [])
    return [point for point in points if isinstance(point, dict)]


def catalog(client, course):
    """List knowledge-homework and exam papers for the AI course task picker."""
    z = course.get("zhs") or {}
    course_id = z.get("courseId")
    class_id = z.get("classId")
    entries = []
    homework_failed = exam_failed = False

    try:
        basic = client.ai_course_basic(course_id, class_id)
        for point in _knowledge_points(basic):
            knowledge_id = point.get("knowledgeId")
            knowledge_name = point.get("knowledgeName") or point.get("name") or "知识点"
            try:
                info = client.ai_homework_info(course_id, class_id, knowledge_id)
            except (CaptchaRequired, AuthenticationExpired):
                raise
            except Exception as exc:
                logger.warning("跳过知识点 %s 的作业：%s", knowledge_name, exc)
                continue
            test_id = _positive_int(info.get("examTestId"))
            paper_id = _positive_int(info.get("paperId"))
            if not test_id or not paper_id:
                logger.warning("跳过缺少试卷标识的知识点：%s", knowledge_name)
                continue
            score = info.get("highMasteryScore")
            try:
                done = float(score) >= 100
            except (TypeError, ValueError):
                done = False
            entries.append({
                "id": "hw-%s-%s-%s" % (knowledge_id, test_id, paper_id),
                "name": "%s · 作业" % knowledge_name,
                "score": score,
                "_completion_status": "submitted" if done else "not_started",
                "zhs": {
                    "kind": "ai_homework",
                    "courseId": course_id,
                    "classId": class_id,
                    "knowledgeId": knowledge_id,
                    "examTestId": test_id,
                    "paperId": paper_id,
                },
            })
    except (CaptchaRequired, AuthenticationExpired):
        raise
    except Exception as exc:
        homework_failed = True
        logger.warning("读取智慧课程作业目录失败：%s", exc)

    try:
        tasks = client.ai_exam_tasks(course_id)
        for task in tasks:
            test_id = _positive_int(task.get("examTestId"))
            paper_id = _positive_int(task.get("examPaperId"))
            task_id = task.get("id")
            user_id = task.get("userId")
            if not test_id or not paper_id or task_id in (None, "") or user_id in (None, ""):
                logger.warning("跳过缺少标识的考试任务：%s", task.get("taskName") or task_id)
                continue
            item = {
                "id": "exam-%s-%s-%s" % (task_id, test_id, paper_id),
                "name": task.get("taskName") or "未命名考试",
                "startTime": task.get("startTime"),
                "endTime": task.get("endTime"),
                "zhs": {
                    "kind": "ai_exam",
                    "courseId": course_id,
                    "classId": class_id,
                    "examTestId": test_id,
                    "examPaperId": paper_id,
                    "taskId": task_id,
                    "userId": user_id,
                },
            }
            if "score" in task:
                item["score"] = task["score"]
            entries.append(item)
    except (CaptchaRequired, AuthenticationExpired):
        raise
    except Exception as exc:
        exam_failed = True
        logger.warning("读取智慧课程考试目录失败：%s", exc)

    if homework_failed and exam_failed:
        raise PlatformUnavailable("智慧树试卷目录读取失败，请稍后重试")
    return [(course, item, 1 if item["zhs"]["kind"] == "ai_homework" else 2)
            for item in entries]
