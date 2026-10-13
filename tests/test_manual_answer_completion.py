"""Manual completion: reuse valid answers, ask the human only for the rest, confirm before posting."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ai.client import AIClient, AIConfig, AIServiceError
from ai.questions import answer_record, model_question, prepare_question
from ai.runner import AnswerRunner, report_path
from AIMoocMain.exam_api import ExamError
from tests.test_ai import FakeClock, question


class RunnerMixin:
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.course = {"id": "ci", "courseId": "c", "courseName": "课程"}
        self.item = {"id": "exam", "name": "测验"}
        self.api = Mock(user_id="user")
        self.api.records.return_value = []
        self.api.verify_submitted.return_value = True
        self.paper = [self.q(i) for i in range(20)]
        self.api.paper.return_value = {"questions": self.paper,
                                       "taskExamRecord": {"id": "task", "status": 0}}
        self.ai = Mock()
        self.ai.config.model = "model"
        self.ai.answer.return_value = {"answer": "A", "confidence": .9, "explanation": "ok"}
        sleep = patch("ai.runner.time.sleep")
        sleep.start()
        self.addCleanup(sleep.stop)

    @staticmethod
    def q(i):
        return dict(question(qid=str(i)), title=f"题{i}")

    def run_paper(self, submit=True, **options):
        runner = AnswerRunner(self.api, self.ai, self.temp.name, auto_submit=submit,
                              clock_factory=FakeClock, output=Mock(), **options)
        return runner.run_paper(self.course, self.item, 3)

    def saved_report(self):
        return json.loads(next(Path(self.temp.name).rglob("*.json")).read_text(encoding="utf-8"))

    def write_previous(self, rows, user="user", task_id="task", exam_id="exam", status="needs_review"):
        path = report_path(self.temp.name, user, self.course, exam_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"paper": "测验", "exam_id": exam_id, "category": 3, "status": status,
                                    "task_id": task_id, "answers": rows}, ensure_ascii=False), encoding="utf-8")

    def row(self, position, title=None, answer="A", fingerprint=True, source="ai"):
        prepared = prepare_question(dict(question(qid=str(position)), title=title or f"题{position}"), position)
        item = {"title": prepared["title"], "question_number": position + 1,
                "options": model_question(prepared)["options"],
                "answer": answer, "record": answer_record(prepared, answer), "source": source}
        if fingerprint:
            from ai.questions import question_fingerprint
            item["question_fingerprint"] = question_fingerprint(prepared)
        else:
            item["record"]["paperId"] = str(position)
        return item


class ReuseTests(RunnerMixin, unittest.TestCase):
    """Legacy rows carry no fingerprint, so they must be verified against the fresh paper."""

    def test_unchanged_questions_are_reused_and_only_the_failed_one_is_asked_again(self):
        self.write_previous([self.row(i) for i in range(19)] + [
            {"title": "题19", "question_number": 20, "error": "AI 未提供答案"}])
        self.ai.answer.return_value = {"answer": None, "confidence": .9, "explanation": "缺少材料"}
        prompts = []
        report = self.run_paper(manual_answer=lambda q, reason: prompts.append((q, reason)) or "B",
                                confirm_submit=lambda *args: True)
        self.assertEqual(self.ai.answer.call_count, 1)
        self.assertEqual(len(prompts), 1)
        self.assertEqual(prompts[0][0]["title"], "题19")
        self.assertTrue(prompts[0][1])
        self.assertEqual(prompts[0][1], "AI 未提供答案")
        entries = self.api.submit.call_args.args[0]["taskExamProblemRecordList"]
        self.assertEqual(len(entries), 20)
        self.api.submit.assert_called_once()
        self.assertEqual([row["source"] for row in report["answers"]], ["ai"] * 19 + ["manual"])

    def test_changed_title_or_option_regenerates_only_that_question(self):
        # Fingerprinted rows survive until their own content changes.
        self.paper = [self.q(i) for i in range(3)]
        self.api.paper.return_value["questions"] = self.paper
        self.write_previous([self.row(i) for i in range(3)])
        options = json.loads(self.paper[1]["dataJson"])
        options[0]["Content"] = "改过的选项"
        self.paper[1]["dataJson"] = json.dumps(options)
        self.paper[2]["title"] = "改过的题干"
        report = self.run_paper(False)
        self.assertEqual(self.ai.answer.call_count, 2)
        self.assertEqual(sorted(call.args[0]["title"] for call in self.ai.answer.call_args_list),
                         ["改过的题干", "题1"])
        self.assertEqual(report["answers"][0]["title"], "题0")

    def test_changed_blank_count_regenerates_that_question(self):
        self.paper = [dict(question(4, "fill"), title="填空")]
        self.api.paper.return_value["questions"] = self.paper
        self.ai.answer.return_value = {"answer": ["钢琴", "小提琴"], "confidence": .9, "explanation": ""}
        self.assertEqual(self.run_paper(False)["status"], "preview")
        self.ai.answer.reset_mock()
        self.paper[0]["answerNum"] = 3
        self.ai.answer.return_value = {"answer": ["a", "b", "c"], "confidence": .9, "explanation": ""}
        self.assertEqual(self.run_paper(False)["status"], "preview")
        self.assertEqual(self.ai.answer.call_count, 1)

    def test_legacy_rows_without_a_fingerprint_are_reused_only_when_verifiable(self):
        legacy = self.row(0, fingerprint=False)
        self.write_previous([legacy])
        self.paper = [self.q(0)]
        self.api.paper.return_value["questions"] = self.paper
        report = self.run_paper(False)
        self.assertEqual(self.ai.answer.call_count, 0)
        self.assertEqual(report["answers"][0]["source"], "ai")
        self.assertEqual(report["answers"][0]["answer"], "A")
        # A changed title or option list is not the same question.
        for change in ("title", "options"):
            with self.subTest(change=change):
                self.paper[0]["title"] = "改过的题干" if change == "title" else self.paper[0]["title"]
                if change == "options":
                    options = json.loads(self.paper[0]["dataJson"])
                    options[0]["Content"] = "另一个选项"
                    self.paper[0]["dataJson"] = json.dumps(options)
                self.ai.answer.reset_mock()
                self.run_paper(False)
                self.assertEqual(self.ai.answer.call_count, 1)

    def test_legacy_row_with_another_paper_id_or_invalid_answer_is_not_reused(self):
        self.paper = [self.q(0)]
        self.api.paper.return_value["questions"] = self.paper
        legacy = self.row(0, fingerprint=False)
        legacy["record"]["paperId"] = "another-paper"
        self.write_previous([legacy])
        self.run_paper(False)
        self.assertEqual(self.ai.answer.call_count, 1)
        self.ai.answer.reset_mock()
        legacy = self.row(0, fingerprint=False)
        legacy["record"]["answer"] = "999"
        legacy["answer"] = "Z"
        self.write_previous([legacy])
        self.run_paper(False)
        self.assertEqual(self.ai.answer.call_count, 1)

    def test_another_task_another_account_or_another_exam_reuses_nothing(self):
        self.addCleanup(lambda: [p.unlink() for p in Path(self.temp.name).rglob("*.json")])
        rows = [self.row(i, fingerprint=False) for i in range(3)]
        self.paper = [self.q(i) for i in range(3)]
        self.api.paper.return_value["questions"] = self.paper
        for kwargs in ({"task_id": "older-task"}, {"user": "other-user"}, {"exam_id": "other-exam"}):
            with self.subTest(**kwargs):
                for existing in Path(self.temp.name).rglob("*.json"):
                    existing.unlink()
                self.write_previous(rows, **kwargs)
                self.ai.answer.reset_mock()
                self.run_paper(False)
                self.assertEqual(self.ai.answer.call_count, 3)

    def test_a_legacy_report_without_source_is_labelled_ai_not_manual(self):
        self.paper = [self.q(0)]
        self.api.paper.return_value["questions"] = self.paper
        row = self.row(0, fingerprint=False)
        row.pop("source")
        self.write_previous([row], status="preview")
        report = self.run_paper(False)
        self.assertEqual(report["answers"][0]["source"], "ai")
        markdown = next(Path(self.temp.name).rglob("*.md")).read_text(encoding="utf-8")
        self.assertIn("AI 答案：", markdown)
        self.assertNotIn("人工答案：", markdown)


class ManualCompletionTests(RunnerMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.paper = [self.q(i) for i in range(3)]
        self.api.paper.return_value["questions"] = self.paper

    def fail_second(self):
        self.ai.answer.side_effect = [{"answer": "A", "confidence": .9, "explanation": ""},
                                      {"answer": None, "confidence": .9, "explanation": "缺少材料"},
                                      {"answer": "B", "confidence": .9, "explanation": ""}]

    def test_human_answer_completes_the_paper_and_posts_every_record_after_confirmation(self):
        self.fail_second()
        confirmations = []
        prompts = []
        report = self.run_paper(manual_answer=lambda q, reason: prompts.append((q, reason)) or "B",
                                confirm_submit=lambda paper, done, total: confirmations.append(
                                    (paper, done, total)) or True)
        self.assertEqual(report["status"], "submitted")
        self.assertEqual(confirmations, [("测验", 3, 3)])
        self.assertEqual(len(prompts), 1)
        self.assertEqual(prompts[0][0]["options"][0]["label"], "A")
        self.assertEqual([row["source"] for row in report["answers"]], ["ai", "manual", "ai"])
        self.assertEqual(report["answers"][1]["answer"], "B")
        entries = self.api.submit.call_args.args[0]["taskExamProblemRecordList"]
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[1]["answer"], "0")
        self.api.submit.assert_called_once()
        self.assertNotIn("pending_manual", self.saved_report())
        markdown = next(Path(self.temp.name).rglob("*.md")).read_text(encoding="utf-8")
        self.assertIn("人工答案：", markdown)
        self.assertIn("AI 答案：", markdown)
        self.assertIn("人工补答", markdown)

    def test_declining_confirmation_saves_answers_without_posting(self):
        self.fail_second()
        report = self.run_paper(manual_answer=lambda q, reason: "B",
                                confirm_submit=lambda *args: False)
        self.assertEqual(report["status"], "preview")
        self.api.submit.assert_not_called()
        saved = self.saved_report()
        self.assertEqual(saved["answers"][1]["source"], "manual")
        self.assertEqual(saved["answers"][1]["answer"], "B")

    def test_declining_then_resuming_posts_once_reusing_both_ai_and_manual_answers(self):
        self.fail_second()
        self.run_paper(manual_answer=lambda q, reason: "B", confirm_submit=lambda *args: False)
        self.ai.answer.reset_mock()
        self.ai.answer.side_effect = None
        self.ai.answer.return_value = {"answer": "A", "confidence": .9, "explanation": ""}
        prompts = []
        report = self.run_paper(manual_answer=lambda q, reason: prompts.append(reason) or "B",
                                confirm_submit=lambda *args: True)
        self.assertEqual(report["status"], "submitted")
        self.assertEqual(self.ai.answer.call_count, 0)
        self.assertEqual(prompts, [])
        entries = self.api.submit.call_args.args[0]["taskExamProblemRecordList"]
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[1]["answer"], "0")
        self.api.submit.assert_called_once()

    def test_leaving_the_prompt_pauses_and_keeps_the_draft_answerable(self):
        self.fail_second()
        events = []
        report = self.run_paper(manual_answer=lambda q, reason: None,
                                confirm_submit=lambda *args: events.append("confirm") or True)
        self.assertEqual(report["status"], "paused")
        self.assertEqual(events, [])
        self.api.submit.assert_not_called()
        saved = self.saved_report()
        self.assertEqual(saved["status"], "paused")
        self.assertEqual([row["question_number"] for row in saved["pending_manual"]], [2])
        self.assertEqual(saved["pending_manual"][0]["title"], "题1")
        self.assertEqual(saved["pending_manual"][0]["reason"], "AI 未提供答案")
        self.assertEqual(saved["answers"][0]["source"], "ai")
        self.assertNotIn("source", saved["answers"][1])
        self.assertEqual(saved["answers"][2]["source"], "ai")

    def test_eof_and_keyboard_interrupt_checkpoint_without_submitting(self):
        for stop in (EOFError(), KeyboardInterrupt()):
            with self.subTest(stop=type(stop).__name__):
                self.fail_second()
                with self.assertRaises(type(stop)):
                    self.run_paper(manual_answer=Mock(side_effect=stop), confirm_submit=lambda *args: True)
                self.api.submit.assert_not_called()
                self.assertEqual(self.saved_report()["status"], "paused")
                self.assertIn("pending_manual", self.saved_report())
                self.api.paper.return_value["taskExamRecord"]["id"] += "-next"

    def test_a_service_failure_never_prompts_and_stops_the_paper(self):
        self.ai.answer.side_effect = AIServiceError("HTTP 401")
        manual = Mock()
        report = self.run_paper(manual_answer=manual, confirm_submit=lambda *args: True)
        self.assertEqual(report["status"], "ai_error")
        manual.assert_not_called()
        self.api.submit.assert_not_called()

    def test_unsupported_questions_are_never_prompted_and_block_submission(self):
        self.paper.append(question(12, "file"))
        manual = Mock()
        report = self.run_paper(manual_answer=manual, confirm_submit=lambda *args: True)
        self.assertEqual(report["status"], "needs_review")
        manual.assert_not_called()
        self.api.submit.assert_not_called()

    def test_an_invalid_human_answer_is_reported_and_never_submitted(self):
        self.fail_second()
        report = self.run_paper(manual_answer=lambda q, reason: "Z", confirm_submit=lambda *args: True)
        self.assertEqual(report["status"], "needs_review")
        self.assertIn("未知选项", report["answers"][1]["error"])
        self.api.submit.assert_not_called()

    def test_a_single_unanswered_question_pauses_instead_of_posting_a_partial_paper(self):
        self.paper = [self.q(0), self.q(1)]
        self.api.paper.return_value["questions"] = self.paper
        self.ai.answer.side_effect = [{"answer": "A", "confidence": .9, "explanation": ""},
                                      {"answer": None, "confidence": .9, "explanation": ""}]
        report = self.run_paper(manual_answer=lambda q, reason: None, confirm_submit=lambda *args: True)
        self.assertEqual(report["status"], "paused")
        self.api.submit.assert_not_called()
        self.assertEqual(len(self.saved_report()["answers"]), 2)

    def test_a_deadline_reached_while_the_human_waits_blocks_submission(self):
        self.fail_second()
        clock = Mock(elapsed=30)
        clock.start.return_value = clock

        def expire(*_):
            raise ExamError("试卷剩余时间已用尽，停止交卷；请在网页核对状态")
        clock.check.side_effect = expire
        runner = AnswerRunner(self.api, self.ai, self.temp.name, auto_submit=True, output=Mock(),
                              clock_factory=lambda *args: clock, manual_answer=lambda q, reason: "B",
                              confirm_submit=lambda *args: True)
        report = runner.run_paper(self.course, self.item, 3)
        self.assertEqual(report["status"], "error")
        self.api.submit.assert_not_called()

    def test_a_pure_ai_paper_never_asks_for_confirmation(self):
        confirm = Mock()
        report = self.run_paper(confirm_submit=confirm)
        self.assertEqual(report["status"], "submitted")
        confirm.assert_not_called()
        self.api.submit.assert_called_once()


class RecordingClock(FakeClock):
    """FakeClock that remembers whether the attempt was stopped and can expire on demand."""

    def __init__(self, *args):
        super().__init__(*args)
        self.stop_called = False
        self.expired = False

    def check(self):
        if self.expired:
            raise ExamError("试卷剩余时间已用尽，停止交卷；请在网页核对状态")

    def stop(self):
        self.stop_called = True


class ClockLifetimeTests(RunnerMixin, unittest.TestCase):
    """The clock runs through the manual prompt and the confirmation; only the POST ends it."""

    def setUp(self):
        super().setUp()
        self.paper = [self.q(i) for i in range(3)]
        self.api.paper.return_value["questions"] = self.paper
        self.clock = RecordingClock()
        self.ai.answer.side_effect = [{"answer": "A", "confidence": .9, "explanation": ""},
                                      {"answer": None, "confidence": .9, "explanation": "缺少材料"},
                                      {"answer": "B", "confidence": .9, "explanation": ""}]

    def run_with_clock(self, **options):
        runner = AnswerRunner(self.api, self.ai, self.temp.name, auto_submit=True, output=Mock(),
                              clock_factory=lambda *args: self.clock, **options)
        return runner.run_paper(self.course, self.item, 3)

    def test_the_clock_keeps_running_until_the_submission_request(self):
        seen = {}

        def manual(question, reason):
            seen["manual"] = self.clock.stop_called
            return "B"

        def confirm(*args):
            seen["confirm"] = self.clock.stop_called
            return True

        def submit(payload):
            seen["submit"] = self.clock.stop_called

        self.api.submit.side_effect = submit
        report = self.run_with_clock(manual_answer=manual, confirm_submit=confirm)
        self.assertEqual(report["status"], "submitted")
        self.assertEqual(seen, {"manual": False, "confirm": False, "submit": True})
        self.assertTrue(self.clock.stop_called)

    def test_an_expiry_after_the_human_answered_still_keeps_the_typed_answer(self):
        def manual(question, reason):
            self.clock.expired = True
            return "B"

        report = self.run_with_clock(manual_answer=manual, confirm_submit=lambda *args: True)
        self.assertEqual(report["status"], "error")
        self.api.submit.assert_not_called()
        saved = self.saved_report()
        self.assertEqual(saved["answers"][1]["source"], "manual")
        self.assertEqual(saved["answers"][1]["answer"], "B")
        self.assertNotIn(2, [row["question_number"] for row in saved.get("pending_manual", [])])


class ParallelManualTests(RunnerMixin, unittest.TestCase):
    """Every already-computed parallel answer is in the report before the human is asked."""

    def run_parallel(self, manual_answer):
        from tests.test_ai_retry import response
        from tests.test_ai_concurrency import Transport
        paper = [self.q(i) for i in range(4)]
        self.api.paper.return_value["questions"] = paper

        def handle(payload):
            if payload["title"] == "题1":
                return response(content='{"answer":null,"confidence":0.9,"explanation":"缺少材料"}')
            return response(content='{"answer":"A","confidence":0.9,"explanation":"ok"}')
        transport = Transport(handle)
        ai = AIClient(AIConfig("https://example.org/v1", "model", "fake-key", api_format="chat_completions"),
                      session=Mock())
        runner = AnswerRunner(self.api, ai, self.temp.name, auto_submit=True, clock_factory=FakeClock,
                              output=Mock(), max_workers=2, manual_answer=manual_answer,
                              confirm_submit=lambda *args: True)
        with patch("ai.client.requests.Session", side_effect=transport.session):
            return runner.run_paper(self.course, self.item, 3)

    def test_all_parallel_answers_are_saved_before_the_manual_prompt(self):
        seen = []

        def manual(question, reason):
            saved = self.saved_report()
            seen.append([row.get("source") for row in saved["answers"]])
            return "B"
        report = self.run_parallel(manual)
        self.assertEqual(report["status"], "submitted")
        self.assertEqual(len(seen), 1)
        self.assertEqual(len(seen[0]), 4)
        self.assertEqual(seen[0], ["ai", None, "ai", "ai"], seen[0])
        self.assertEqual([row["source"] for row in report["answers"]], ["ai", "manual", "ai", "ai"])
        self.assertEqual(len(self.api.submit.call_args.args[0]["taskExamProblemRecordList"]), 4)
        self.api.submit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
