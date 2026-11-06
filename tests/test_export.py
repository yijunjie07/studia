"""Offline integration checks for the imported PR #198 export paths."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from docx import Document
from AIMoocMain.export_questions import QuizExportHandler, parse_index_input


class ExportTests(unittest.TestCase):
    def test_exact_papers_can_merge_without_exporting_unselected_tasks(self):
        for merged in (False, True):
            with self.subTest(merged=merged), tempfile.TemporaryDirectory() as tmp:
                first = {"id": "i1", "courseId": "c1", "courseName": "英语"}
                second = {"id": "i2", "courseId": "c2", "courseName": "计算机"}
                selected = [(first, {"id": "a", "name": "作业一"}, 1),
                            (first, {"id": "b", "name": "测验二"}, 3),
                            (second, {"id": "a", "name": "计算机测验"}, 3)]
                api = Mock(user_id="user")
                api.get_exam_paper.return_value = {"questions": [{"id": "q", "typeId": 3, "title": "题目", "stdAnswer": "0"}]}
                api.get_exam_student_records.return_value = []
                self.assertIn("selected_papers", __import__("inspect").signature(QuizExportHandler).parameters,
                              "export must accept exact course/task selection")
                events = []
                QuizExportHandler(client=api, course_rows=[first, second], selected_papers=selected,
                                  output_dir=tmp, quiz_mode="merged" if merged else "per_chapter",
                                  on_progress=events.append)
                api.get_exam_list_by_student.assert_not_called()
                self.assertEqual(api.get_exam_paper.call_count, 3)
                paths = list(Path(tmp).rglob("*.md"))
                self.assertEqual(len(paths), 2 if merged else 3)
                english = "\n".join(p.read_text() for p in Path(tmp, "英语").glob("*.md"))
                self.assertIn("作业一", english)
                self.assertIn("测验二", english)
                self.assertNotIn("计算机测验", english)
                self.assertEqual([e.status for e in events if e.kind == "result"], ["success"] * 3)

    def test_explicit_empty_selection_exports_nothing(self):
        api = Mock(user_id="user")
        self.assertIn("selected_papers", __import__("inspect").signature(QuizExportHandler).parameters)
        with tempfile.TemporaryDirectory() as tmp:
            QuizExportHandler(client=api, course_rows=[{"id": "i", "courseId": "c", "courseName": "课程"}],
                              selected_papers=[], output_dir=tmp)
            self.assertEqual(list(Path(tmp).rglob("*.md")), [])
        api.get_exam_list_by_student.assert_not_called()
        api.get_exam_paper.assert_not_called()

    def test_markdown_and_word_export_from_mock_platform(self):
        api = Mock()
        api.user_id = "user"
        api.get_exam_list_by_student.return_value = {"code": 200, "rows": [{"id": "exam", "name": "音乐测验"}]}
        api.get_exam_paper.return_value = {"code": 200, "data": {
            "questions": [{"id": "q", "typeId": 3, "title": "测试判断题", "stdAnswer": "0"}],
        }}
        api.get_exam_student_records.return_value = []
        with tempfile.TemporaryDirectory() as tmp:
            QuizExportHandler(client=api, course_rows=[{"id": "info", "courseId": "course", "courseName": "测试课程"}],
                              category_ids=[3], output_dir=tmp, export_format="both")
            markdown = list(Path(tmp).rglob("*.md"))
            word = list(Path(tmp).rglob("*.docx"))
            self.assertTrue(markdown)
            self.assertTrue(word)
            self.assertIn("错误", markdown[0].read_text())
            text = "\n".join(p.text for p in Document(word[0]).paragraphs)
            self.assertIn("测试判断题", text)
            self.assertIn("错误", text)
            self.assertFalse(list(Path(tmp).rglob("*.json")))

    def test_selection_parser(self):
        self.assertEqual(parse_index_input("1,3", 3), [1, 3])
        self.assertEqual(parse_index_input("all", 2), [1, 2])
        self.assertIsNone(parse_index_input("999", 2))


if __name__ == "__main__":
    unittest.main()
