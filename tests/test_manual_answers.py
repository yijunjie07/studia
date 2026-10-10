"""An unresolved question can be completed manually without losing other work."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ai.client import AIResponseError, AIServiceError, AITransientServiceError
from ai.runner import AnswerRunner
from AIMoocMain.exam_api import ExamError
from tests.test_ai import FakeClock, question


class ManualAnswerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.course = {"id": "ci", "courseId": "c"}
        self.item = {"id": "exam"}
        self.api = Mock(user_id="user")
        self.api.records.return_value = []
        self.api.verify_submitted.return_value = True
        self.api.paper.return_value = {"questions": [dict(question(qid=str(i)), title=f"题{i}") for i in range(3)],
                                       "taskExamRecord": {"id": "task", "status": 0}}
        self.good = {"answer": "A", "confidence": .95, "explanation": "ok"}
        self.ai = Mock()
        self.ai.config.model = "model"
        self.ai.answer.return_value = self.good
        self.manual = Mock(return_value="B")
        sleep = patch("ai.runner.time.sleep")
        sleep.start()
        self.addCleanup(sleep.stop)

    def run_paper(self, submit=True, clock_factory=FakeClock, threshold=.8):
        runner = AnswerRunner(self.api, self.ai, self.temp.name, auto_submit=submit,
                              min_confidence=threshold, clock_factory=clock_factory,
                              output=Mock(), manual_answer=self.manual)
        return runner.run_paper(self.course, self.item, 3)

    def test_retry_exhaustion_shows_only_failed_question_then_submits(self):
        self.ai.answer.side_effect = [self.good] + [AIResponseError("bad JSON") for _ in range(3)] + [self.good]
        report = self.run_paper()
        self.assertEqual(report["status"], "submitted")
        self.assertEqual(self.ai.answer.call_count, 5)
        self.manual.assert_called_once()
        self.assertEqual(self.manual.call_args.args[0]["number"], 1)
        self.assertEqual(report["answers"][1]["source"], "manual")
        self.assertIsNone(report["answers"][1]["confidence"])
        self.assertNotIn("error", report["answers"][1])
        entries = self.api.submit.call_args.args[0]["taskExamProblemRecordList"]
        self.assertEqual([entry["answer"] for entry in entries], ["3", "0", "3"])
        self.api.submit.assert_called_once()

    def test_low_confidence_goes_to_manual_without_rerolling(self):
        self.ai.answer.side_effect = [dict(self.good, confidence=.2), self.good, self.good]
        self.assertEqual(self.run_paper()["status"], "submitted")
        self.assertEqual(self.ai.answer.call_count, 3)
        self.manual.assert_called_once()

    def test_temporary_service_failure_can_be_answered_manually_after_retries(self):
        self.ai.answer.side_effect = [AITransientServiceError("timeout") for _ in range(3)] + [self.good, self.good]
        self.assertEqual(self.run_paper()["status"], "submitted")
        self.manual.assert_called_once()

    def test_fixed_authentication_retries_ai_after_restart(self):
        self.ai.answer.side_effect = AIServiceError("HTTP 401")
        self.assertEqual(self.run_paper()["status"], "ai_error")
        self.ai.answer.reset_mock(side_effect=True)
        self.assertEqual(self.run_paper()["status"], "submitted")
        self.assertEqual(self.ai.answer.call_count, 3)
        self.manual.assert_not_called()

    def test_changed_options_invalidate_saved_answer(self):
        self.run_paper(False)
        self.ai.answer.reset_mock()
        options = json.loads(self.api.paper.return_value["questions"][0]["dataJson"])
        options[0]["Content"] = "新选项"
        self.api.paper.return_value["questions"][0]["dataJson"] = json.dumps(options)
        self.assertEqual(self.run_paper()["status"], "submitted")
        self.ai.answer.assert_called_once()

    def test_parent_context_changes_invalidate_subquestion_cache(self):
        self.api.paper.return_value["questions"] = [{"id": "parent", "title": "旧材料",
                                                   "questionSubList": [question(qid="child")]}]
        self.run_paper(False)
        self.api.paper.return_value["questions"][0]["title"] = "新材料"
        self.ai.answer.reset_mock()
        self.assertEqual(self.run_paper()["status"], "submitted")
        self.ai.answer.assert_called_once()

    def test_pause_keeps_later_cached_answers_for_next_resume(self):
        self.ai.answer.side_effect = [self.good, dict(self.good, confidence=.85), self.good]
        self.run_paper(False)
        self.ai.answer.reset_mock(side_effect=True)
        self.manual.return_value = None
        self.assertEqual(self.run_paper(threshold=.9)["status"], "paused")
        self.manual.return_value = "B"
        self.assertEqual(self.run_paper(threshold=.9)["status"], "submitted")
        self.ai.answer.assert_not_called()

    def test_pause_and_restart_preserve_completed_answers_and_pending_question(self):
        self.ai.answer.side_effect = [self.good] + [AIResponseError("bad JSON") for _ in range(3)]
        self.manual.return_value = None
        report = self.run_paper()
        self.assertEqual(report["status"], "paused")
        self.assertEqual(len(report["answers"]), 2)
        self.api.submit.assert_not_called()
        self.ai.answer.reset_mock(side_effect=True)
        self.ai.answer.return_value = self.good
        self.manual.reset_mock()
        self.manual.return_value = "B"
        report = self.run_paper()
        self.assertEqual(report["status"], "submitted")
        self.assertEqual(self.ai.answer.call_count, 1)
        self.assertEqual(self.ai.answer.call_args.args[0]["title"], "题2")
        self.manual.assert_called_once()
        self.api.submit.assert_called_once()

    def test_legacy_preview_report_reuses_valid_standalone_answers(self):
        self.assertEqual(self.run_paper(False)["status"], "preview")
        path = next(Path(self.temp.name).rglob("*.json"))
        previous = json.loads(path.read_text())
        for answer in previous["answers"]:
            answer.pop("question_fingerprint", None)
        path.write_text(json.dumps(previous))
        self.ai.answer.reset_mock()
        self.assertEqual(self.run_paper()["status"], "submitted")
        self.ai.answer.assert_not_called()
        self.api.submit.assert_called_once()

    def test_changed_question_invalidates_only_its_cached_answer(self):
        self.run_paper(False)
        self.ai.answer.reset_mock()
        self.api.paper.return_value["questions"][1]["title"] = "改过的题干"
        self.assertEqual(self.run_paper()["status"], "submitted")
        self.ai.answer.assert_called_once()
        self.assertEqual(self.ai.answer.call_args.args[0]["title"], "改过的题干")

    def test_higher_threshold_requires_manual_review_of_saved_low_confidence(self):
        self.ai.answer.return_value = dict(self.good, confidence=.85)
        self.run_paper(False)
        self.ai.answer.reset_mock()
        self.assertEqual(self.run_paper(threshold=.9)["status"], "submitted")
        self.ai.answer.assert_not_called()
        self.assertEqual(self.manual.call_count, 3)

    def test_time_expiry_during_manual_input_blocks_submission(self):
        clock = Mock(elapsed=30)
        clock.start.return_value = clock
        self.ai.answer.return_value = dict(self.good, confidence=.1)
        def answer(*args):
            clock.check.side_effect = ExamError("时间已用尽")
            return "B"
        self.manual.side_effect = answer
        report = self.run_paper(clock_factory=lambda *args: clock)
        self.assertEqual(report["status"], "error")
        self.assertEqual(report["answers"][0]["answer"], "B")
        self.assertEqual(report["answers"][0]["source"], "manual")
        self.api.submit.assert_not_called()

    def test_invalid_manual_answer_cannot_bypass_validation(self):
        self.ai.answer.return_value = dict(self.good, confidence=.1)
        self.manual.return_value = "Z"
        self.assertEqual(self.run_paper()["status"], "paused")
        self.api.submit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
