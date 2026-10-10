"""Offline manual-answer input and compact AI summary regressions."""
import io
import unittest

from rich.console import Console

import theme
from ai.client import AIConfig
from ai.questions import prepare_question
from reporting import ProgressEvent
from ui import TerminalUI


def question(kind=1, **overrides):
    raw = {"id": "q1", "typeId": kind, "title": "请选择答案", "answerNum": 2,
           "dataJson": [{"SortOrder": 4, "Content": "第一个选项"},
                        {"SortOrder": 7, "Content": "第二个选项"},
                        {"SortOrder": 9, "Content": "第三个选项"}]}
    raw.update(overrides)
    return prepare_question(raw, 2)


def make_view(answers, width=52):
    output = io.StringIO()
    values = iter(answers)

    def read():
        value = next(values)
        if isinstance(value, BaseException):
            raise value
        return value

    view = TerminalUI(console=Console(file=output, width=width, theme=theme.THEME), input_fn=read)
    return view, output


class ManualAnswerTests(unittest.TestCase):
    def test_lowercase_b_is_an_answer_and_invalid_selection_is_correctable(self):
        view, output = make_view(["Z", "b"])
        self.assertEqual(view.manual_answer(question(), "未知选项"), "B")
        self.assertIn("第 3 题", output.getvalue())
        self.assertIn("单选题", output.getvalue())
        self.assertIn("第二个选项", output.getvalue())

    def test_multiselect_supports_compact_and_separated_letters(self):
        for raw in ("ac", "a, c", "a c", "a，c"):
            with self.subTest(raw=raw):
                view, _ = make_view([raw])
                self.assertEqual(view.manual_answer(question(2), "置信度不足"), ["A", "C"])

    def test_duplicate_multiple_choices_are_rejected_before_correction(self):
        view, _ = make_view(["AA", "bc"])
        self.assertEqual(view.manual_answer(question(2), ""), ["B", "C"])

    def test_judgement_inputs_are_booleans(self):
        for raw, expected in (("对", True), ("错", False), ("true", True), ("0", False)):
            with self.subTest(raw=raw):
                view, _ = make_view(["也许", raw])
                self.assertIs(view.manual_answer(question(3), ""), expected)

    def test_blanks_are_prompted_individually_and_empty_answer_is_correctable(self):
        for kind in (4, 5):
            with self.subTest(kind=kind):
                view, output = make_view(["", " alpha ", "b"])
                self.assertEqual(view.manual_answer(question(kind), ""), ["alpha", "b"])
                self.assertIn("第 2 空", output.getvalue())

    def test_long_context_title_and_options_are_complete_and_literal(self):
        title = "完整题干" * 70 + "[bold]末尾题干[/bold]"
        option = "完整选项" * 60 + "末尾选项"
        q = question(title=title, dataJson=[{"SortOrder": 1, "Content": option},
                                           {"SortOrder": 2, "Content": "B"}])
        q.update(context="完整材料" * 60 + "末尾材料", child_number=1)
        view, output = make_view(["a"])
        self.assertEqual(view.manual_answer(q, 'provider body: token=secret {"answer": null}'), "A")
        rendered = "".join(output.getvalue().split())
        for content in (title, option, q["context"]):
            self.assertIn(content, rendered)
        self.assertIn("第3题·第2小题", rendered)
        self.assertNotIn("secret", rendered)
        self.assertNotIn("provider", rendered)

    def test_essay_preserves_long_text_and_navigation_letters(self):
        for text in ("b", "q", "长答案。" * 300 + "\n第二段说明。"):
            with self.subTest(length=len(text)):
                view, _ = make_view(["", text])
                self.assertEqual(view.manual_answer(question(6), ""), text)

    def test_live_is_paused_during_input_and_restored_on_answer_or_cancel(self):
        for value, expected in (("b", "B"), (":q", None), (EOFError(), None), (KeyboardInterrupt(), None)):
            with self.subTest(value=value):
                view, output = make_view([])
                with view.activity("正在答题"):
                    live = view.live

                    def read():
                        self.assertIsNone(view.live)
                        self.assertFalse(live.is_started)
                        if isinstance(value, BaseException):
                            raise value
                        return value

                    view.input_fn = read
                    self.assertEqual(view.manual_answer(question(), ""), expected)
                    self.assertIs(view.live, live)
                    self.assertTrue(live.is_started)
                self.assertIsNone(view.live)
                self.assertIn("第二个选项", output.getvalue())

    def test_cancel_during_second_blank_does_not_return_partial_answer(self):
        view, _ = make_view(["first", ":q"])
        self.assertIsNone(view.manual_answer(question(4), ""))


class CompactReviewTests(unittest.TestCase):
    def test_paused_work_is_preserved_without_counting_as_failure(self):
        view, output = make_view([""], width=100)
        view.begin_operation()
        view.on_progress(ProgressEvent("result", "第一章", status="paused"))
        self.assertEqual(view.operation_result(), 1)
        rendered = output.getvalue()
        self.assertIn("失败 0", rendered)
        self.assertIn("待补答 1", rendered)
        self.assertIn("答案已保留", rendered)
        self.assertNotIn("paused", rendered)

    def test_connection_test_stays_available_without_verbose_summary(self):
        view, output = make_view(["t", ""])
        options = {}
        checks = []

        def check():
            checks.append(True)
            return "连接测试通过 · 2026-10-10 12:34:56"

        result = view.review_ai([], AIConfig("https://example.org/v1", "model", "secret"), options,
                                check_connection=check)
        self.assertEqual(result, (True, .8))
        self.assertEqual(checks, [True])
        rendered = output.getvalue()
        for shortcut in ("回车开始", "s 修改设置", "t 测试连接", "b 返回选择", "q 退出"):
            self.assertIn(shortcut, rendered)
        self.assertIn("通过", rendered)
        for clutter in ("ai_results/", "12:34:56", "题干和选项将发送", "开始前自动测试", "secret"):
            self.assertNotIn(clutter, rendered)


if __name__ == "__main__":
    unittest.main()
