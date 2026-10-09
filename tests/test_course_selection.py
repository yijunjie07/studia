import unittest
from unittest.mock import Mock, patch

import StartWork
from AIMoocMain.main import AIMoocHandler
from ZYKMoocMain.main import ZYKMoocHandler


class CourseSelectionTests(unittest.TestCase):
    def setUp(self):
        self.courses = [
            {"id": "a", "courseInfoId": "a", "courseName": "音乐", "courseInfoName": "第1期"},
            {"id": "b", "courseInfoId": "b", "courseName": "音乐", "courseInfoName": "第2期"},
        ]

    def test_choose_by_number_not_course_name(self):
        with patch('builtins.input', return_value='2'):
            self.assertEqual(StartWork.get_course_selection(self.courses), [self.courses[1]])

    def test_empty_input_cancels_and_all_selects_all(self):
        with patch('builtins.input', return_value=''):
            self.assertEqual(StartWork.get_course_selection(self.courses), [])
        with patch('builtins.input', return_value='all'):
            self.assertEqual(StartWork.get_course_selection(self.courses), self.courses)

    def test_study_fetches_before_selection_and_reuses_client(self):
        client = Mock()
        client.my_course_list.return_value = {"rows": self.courses}
        api_class, handler = Mock(return_value=client), Mock()
        def choose(rows):
            client.my_course_list.assert_called_once_with(page_size=9999)
            self.assertEqual(rows, self.courses)
            return [rows[1]]
        with patch.object(StartWork, 'get_login_info', return_value=('', '', 'token')), \
             patch.object(StartWork, 'get_course_selection', side_effect=choose), \
             patch.object(StartWork, 'get_skip_course_config', side_effect=AssertionError('old prompt')):
            StartWork.handle_study_courses(0, api_class, handler)
        handler.assert_called_once_with(client=client, course_rows=[self.courses[1]])

    def test_cancel_never_starts_processing(self):
        client, handler = Mock(), Mock()
        client.my_course_list.return_value = {"rows": self.courses}
        with patch.object(StartWork, 'get_login_info', return_value=('', '', 'token')), \
             patch.object(StartWork, 'get_course_selection', return_value=[]):
            StartWork.handle_study_courses(0, Mock(return_value=client), handler)
        handler.assert_not_called()

    def test_both_handlers_process_only_selected_rows_without_refetch(self):
        for cls in (AIMoocHandler, ZYKMoocHandler):
            with self.subTest(handler=cls.__name__):
                client = Mock()
                with patch.object(cls, 'process_course') as process:
                    cls(client=client, course_rows=[self.courses[1]])
                    process.assert_called_once_with(self.courses[1])
                    client.my_course_list.assert_not_called()
                with patch.object(cls, 'process_course') as process:
                    cls(client=client, course_rows=[])
                    process.assert_not_called()
                    client.my_course_list.assert_not_called()
