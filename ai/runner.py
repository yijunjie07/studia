"""Selected-paper workflow with local reports and verified submission outcomes."""
import hashlib
import json
import math
import os
import threading
import time
from pathlib import Path

from AIMoocMain.exam_api import ExamError
from AIMoocMain.export_questions import get_questions_from_paper, paper_display_name, paper_exam_id, safe_filename
from ai.client import AIError
from ai.questions import answer_record, model_question, prepare_question


class AttemptClock:
    """Report only real elapsed time, at the web client's 10-second interval."""
    def __init__(self, api, course, exam_id, task_id, remaining, enabled):
        self.api, self.course, self.exam_id, self.task_id = api, course, exam_id, task_id
        self.remaining, self.enabled = remaining, enabled
        self.started = time.monotonic()
        self.stop_event = threading.Event()
        self.error = None
        self.thread = None

    def start(self):
        if self.enabled:
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()
        return self

    def _loop(self):
        previous = self.started
        while not self.stop_event.wait(10):
            now = time.monotonic()
            try:
                self.check()
                self.api.heartbeat(self.course, self.exam_id, self.task_id, int(now - previous))
                previous = now
            except ExamError as exc:
                self.error = str(exc)
                return

    def check(self):
        if self.error:
            raise ExamError(self.error)
        if self.remaining is not None and self.elapsed >= self.remaining:
            raise ExamError("试卷剩余时间已用尽，停止交卷；请在网页核对状态")

    @property
    def elapsed(self):
        return max(0, int(time.monotonic() - self.started))

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=45)
            if self.thread.is_alive():
                self.error = "计时请求未结束，停止交卷"


def report_path(root, user_id, course, exam_id):
    identity = "%s/%s/%s" % (user_id, course.get("id") or course.get("courseInfoId"), exam_id)
    digest = hashlib.sha256(identity.encode()).hexdigest()[:20]
    return Path(root) / safe_filename(course.get("courseName", "课程")) / (digest + ".json")


def write_report(path, report):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(temp), str(path))
    lines = ["# " + report["paper"], "", "状态：" + report["status"], "", "AI 生成答案，不是平台标准答案。", ""]
    if report.get("message"):
        lines += [report["message"], ""]
    for index, item in enumerate(report["answers"], 1):
        lines += ["## %d. %s" % (index, item.get("title", "无法解析的题目")), ""]
        for opt in item.get("options", []):
            lines.append("%s. %s" % (opt["label"], opt["text"]))
        lines += ["", "AI 答案：" + json.dumps(item.get("answer"), ensure_ascii=False),
                  "置信度：" + str(item.get("confidence", "")),
                  item.get("explanation", ""), item.get("error", ""), ""]
    path.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")


class AnswerRunner:
    def __init__(self, api, ai, output_dir="ai_results", auto_submit=False, min_confidence=0.8, output=print, clock_factory=AttemptClock):
        if not math.isfinite(min_confidence) or not 0 <= min_confidence <= 1:
            raise ValueError("置信度阈值必须在 0 到 1 之间")
        self.api, self.ai, self.output_dir = api, ai, output_dir
        self.auto_submit, self.min_confidence = auto_submit, min_confidence
        self.output, self.clock_factory = output, clock_factory

    def run_paper(self, course, item, category):
        path = report_path(self.output_dir, self.api.user_id, course, paper_exam_id(item))
        path.parent.mkdir(parents=True, exist_ok=True)
        lock = path.with_suffix(".lock")
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise ExamError("任务已锁定；确认没有其他程序运行并核对网页状态后，才能清理对应 .lock 文件") from None
        try:
            with os.fdopen(fd, "w") as stream:
                stream.write(str(os.getpid()))
            return self._run_paper(course, item, category)
        finally:
            lock.unlink()

    def _run_paper(self, course, item, category):
        exam_id = paper_exam_id(item)
        if not exam_id:
            raise ExamError("试卷缺少 ID")
        if not self.api.user_id or not course.get("courseId") or not (course.get("id") or course.get("courseInfoId")):
            raise ExamError("缺少账号或课程 ID")
        path = report_path(self.output_dir, self.api.user_id, course, exam_id)
        if path.exists():
            try:
                previous = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                raise ExamError("已有报告无法读取，请先检查文件，避免重复交卷") from None
            if previous.get("status") in ("submitting", "submitted", "submission_unknown"):
                self.output("跳过已有交卷记录：%s（%s）" % (paper_display_name(item), previous["status"]))
                return previous
        report = {"course": course.get("courseName", ""), "paper": paper_display_name(item),
                  "exam_id": exam_id, "category": category, "status": "preparing", "answers": [],
                  "auto_submit": self.auto_submit, "model": self.ai.config.model}
        clock = None
        try:
            # Query own attempt history before paper() can create a new attempt.
            records = self.api.records(exam_id)
            if any(str(x.get("status")) != "0" for x in records):
                report.update(status="skipped", message="已有已提交、批阅中或未知状态的作答记录，未再次进入试卷")
                return report
            paper = self.api.paper(exam_id)
            task = paper.get("taskExamRecord") or {}
            if str(paper.get("tjzt")) == "1" or str(task.get("status")) != "0":
                report.update(status="skipped", message="试卷已提交或不处于草稿状态")
                return report
            owner = task.get("userId") or task.get("studentId")
            if owner and str(owner) != str(self.api.user_id):
                raise ExamError("作答记录与当前账号不匹配")
            task_id = task.get("id")
            if not task_id:
                raise ExamError("未取得作答记录 ID，停止处理")
            if str(paper.get("typeId")) == "3" or str(paper.get("questionSettingMethod")) == "3":
                raise ExamError("附件或材料试卷暂不支持自动作答")
            raw_questions = get_questions_from_paper(paper)
            if not raw_questions:
                raise ExamError("试卷为空或结构不受支持")
            # Do not submit a parsed subset of a paper.
            count = paper.get("questionCount")
            if count is not None and int(count) != len(raw_questions):
                raise ExamError("试卷声明题数与解析题数不一致")
            remaining = paper.get("surplusSecond")
            if remaining is not None:
                remaining = int(remaining)
                if remaining <= 0:
                    raise ExamError("试卷已无剩余时间")
            report["task_id"] = str(task_id)
            report["status"] = "answering"
            write_report(path, report)
            clock = self.clock_factory(self.api, course, exam_id, task_id, remaining, self.auto_submit).start()
            entries, identities = [], set()
            failures = 0
            for number, raw in enumerate(raw_questions):
                children = raw.get("questionSubList") if isinstance(raw, dict) else None
                if children is not None and not isinstance(children, list):
                    raise ExamError("子题结构未知")
                work = [(child, raw, i) for i, child in enumerate(children)] if children else [(raw, None, None)]
                for value, parent, child_number in work:
                    clock.check()
                    item_report = {"title": str(value.get("title", "")) if isinstance(value, dict) else "无法解析的题目"}
                    try:
                        q = prepare_question(value, number, parent, child_number)
                        identity = (q["paper_id"], q["paper_sub_id"])
                        if identity in identities:
                            raise ValueError("试卷包含重复试题 ID")
                        identities.add(identity)
                        item_report.update(title=q["title"], options=model_question(q)["options"])
                        self.output("AI 作答 %s / %s：%s" % (number + 1, len(raw_questions), q["title"][:70]))
                        answer = self.ai.answer(model_question(q))
                        item_report.update(answer)
                        if answer["confidence"] < self.min_confidence:
                            raise ValueError("置信度低于设置阈值，需要人工检查")
                        entry = answer_record(q, answer["answer"])
                        entries.append(entry)
                        item_report["record"] = entry
                    except (ValueError, TypeError, AIError) as exc:
                        failures += 1
                        item_report["error"] = str(exc)
                    report["answers"].append(item_report)
                    write_report(path, report)
                    clock.check()
            clock.stop()
            clock.check()
            if failures or not entries:
                report.update(status="needs_review", message="存在未完成或不支持的题目，仅保存本地报告，未交卷")
            elif not self.auto_submit:
                report.update(status="preview", message="答案已保存到本地，未向平台保存或提交答案")
            else:
                # Recheck independently; never overwrite a submission made in a browser.
                if any(str(x.get("status")) != "0" for x in self.api.records(exam_id)):
                    raise ExamError("作答状态已变化，停止交卷")
                clock.check()
                payload = {
                    "courseId": course["courseId"], "courseInfoId": course.get("id") or course.get("courseInfoId"),
                    "examId": exam_id, "examName": paper.get("name") or report["paper"],
                    "device": 1, "categoryId": category, "examTime": clock.elapsed,
                    "groupId": 0, "isLast": True, "id": task_id, "taskExamProblemRecordList": entries,
                }
                # Persist before the irreversible request, including on Ctrl-C or process exit.
                report["status"] = "submitting"
                write_report(path, report)
                self.api.submit(payload)
                if self.api.verify_submitted(exam_id, task_id):
                    report.update(status="submitted", message="平台作答记录已确认交卷")
                else:
                    report.update(status="submission_unknown", message="请求已发送但未确认已交卷状态，请在网页核对；不会自动重发")
        except (ExamError, ValueError, TypeError, KeyError) as exc:
            state = "submission_unknown" if report["status"] == "submitting" else "error"
            report.update(status=state, message=str(exc))
        finally:
            if clock:
                clock.stop()
            write_report(path, report)
            self.output("%s：%s；报告 %s" % (report["paper"], report["status"], path))
            if report.get("message"):
                self.output("原因：%s" % report["message"])
        return report
