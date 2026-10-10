"""Recognize attachment homework from the platform catalog, not task names."""
import unittest

from task_capabilities import is_attachment_task, task_type_label


class TaskCapabilitiesTests(unittest.TestCase):
    def test_attachment_catalog_enum_accepts_numeric_and_string_values(self):
        for value in (3, "3"):
            with self.subTest(type_id=value):
                item = {"id": "attachment", "name": "实验报告", "typeId": value}
                self.assertTrue(is_attachment_task(item, 1))
                self.assertEqual(task_type_label(item, 1), "附件作业")

    def test_shared_card_type_does_not_depend_on_catalog_category(self):
        for category in (1, 2, 3):
            with self.subTest(category=category):
                self.assertTrue(is_attachment_task({"typeId": 3}, category))

    def test_names_and_unrelated_type_fields_do_not_disable_normal_papers(self):
        for item in ({"name": "附件作业操作练习", "typeId": 1},
                     {"name": "附件作业"},
                     {"typeId": 1, "questionSettingMethod": 3},
                     {"examType": 3, "taskType": 3, "type": 3}):
            with self.subTest(item=item):
                self.assertFalse(is_attachment_task(item, 1))
                self.assertEqual(task_type_label(item, 1), "作业")

    def test_unknown_and_other_types_remain_available(self):
        for value in (None, "", False, True, 0, 1, "1", 2, 4, 99, "unknown", [], {}):
            with self.subTest(type_id=value):
                self.assertFalse(is_attachment_task({"typeId": value}, 1))

    def test_ordinary_tasks_preserve_category_labels(self):
        for category, label in ((1, "作业"), (2, "考试"), (3, "测验"), (9, "9")):
            with self.subTest(category=category):
                self.assertEqual(task_type_label({}, category), label)


if __name__ == "__main__":
    unittest.main()
