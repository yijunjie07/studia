"""Offline integration checks for the imported PR #198 export paths."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from docx import Document
from AIMoocMain.export_questions import QuizExportHandler, parse_index_input


class ExportTests(unittest.TestCase):
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
