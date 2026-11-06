"""Read-only task completion status and its visible selection column."""
import io
import unittest
from unittest.mock import Mock

from rich.console import Console

import theme
from app import Application
from ui import TerminalUI


COURSE = {'id': 'ci', 'courseId': 'c', 'courseName': '课程'}


class TaskStatusTests(unittest.TestCase):
    def catalog(self, histories):
        client = Mock(user_id='student', default_base_url='https://platform.invalid', access_token='test')
        view = TerminalUI(console=Console(file=io.StringIO(), theme=theme.THEME))
        app = Application(view, store=Mock())
        from unittest.mock import patch

        def request(session, method, endpoint, **kwargs):
            self.assertEqual(method, 'GET')
            if endpoint == '/course/exam/record/getExamListByStudent':
                rows = [{'id': key, 'name': key} for key in histories] if kwargs['params']['categoryId'] == 1 else []
                return {'rows': rows}
            self.assertEqual(endpoint, '/course/exam/record/getStudentRecordByExamId')
            self.assertEqual(kwargs['params']['studentId'], 'student')
            result = histories[kwargs['params']['examId']]
            if isinstance(result, Exception):
                raise result
            return result

        with patch('AIMoocMain.exam_api.ExamAPI.request', autospec=True, side_effect=request):
            return app.task_catalog(client, [COURSE])

    def test_catalog_distinguishes_submitted_draft_and_no_attempts(self):
        rows = self.catalog({'交卷后有草稿': [{'status': 0}, {'status': '2'}],
                             '只有草稿': [{'status': '0'}], '没有作答': []})
        self.assertEqual([item.get('_completion_status') for _, item, _ in rows],
                         ['submitted', 'draft', 'not_started'])

    def test_unknown_or_failed_history_never_means_not_started(self):
        from AIMoocMain.exam_api import ExamError
        rows = self.catalog({'未知状态': [{'status': 7}], '缺少状态': [{}],
                             '异常结构': {'unexpected': []}, '失败': ExamError('读取失败'),
                             '已交卷': [{'status': 2}]})
        self.assertEqual([item.get('_completion_status') for _, item, _ in rows],
                         ['unknown', 'unknown', 'unknown', 'unknown', 'submitted'])

    def test_status_is_visible_without_losing_selection_or_narrow_layout(self):
        from rich.cells import cell_len
        rows = self.catalog({'已做任务': [{'status': 2}], '未做任务': []})
        output = io.StringIO()
        view = TerminalUI(console=Console(file=output, width=52, height=30, theme=theme.THEME),
                          input_fn=lambda: '1')
        self.assertEqual(view.papers(rows, refresh=True), [rows[0]])
        rendered = output.getvalue()
        self.assertIn('已提交', rendered)
        self.assertIn('未作答', rendered)
        self.assertIn('刷新状态', rendered)
        self.assertTrue(all(cell_len(line) <= 52 for line in rendered.splitlines()))

    def test_refresh_reloads_history_in_place(self):
        from unittest.mock import patch
        from course_flow import CourseWorkspace
        from ui import Cancelled
        output = io.StringIO()
        answers = iter(['r', 'q'])
        view = TerminalUI(console=Console(file=output, width=80, height=30, theme=theme.THEME),
                          input_fn=lambda: next(answers))
        store = Mock()
        store.get.side_effect = lambda key, default=None: default
        app = Application(view, store=store)
        workspace = CourseWorkspace(app)
        workspace.client = Mock(user_id='student', default_base_url='https://platform.invalid', access_token='test')
        histories = iter([[], [{'status': 2}]])

        def request(session, method, endpoint, **kwargs):
            self.assertEqual(method, 'GET')
            if endpoint == '/course/exam/record/getExamListByStudent':
                return {'rows': [{'id': 'a', 'name': '第一章'}] if kwargs['params']['categoryId'] == 1 else []}
            self.assertEqual(endpoint, '/course/exam/record/getStudentRecordByExamId')
            return next(histories)

        with patch('AIMoocMain.exam_api.ExamAPI.request', autospec=True, side_effect=request):
            with self.assertRaises(Cancelled):
                workspace.tasks([COURSE], 2, {})
        before, after = output.getvalue().split('已提交', 1)
        self.assertIn('未作答', before)
        self.assertNotIn('未作答', after)

    def test_refresh_preserves_selection_when_status_changes(self):
        from course_flow import CourseWorkspace
        from ui import Cancelled
        answers = iter(['all', 'b', 'r', '', 'q'])
        view = TerminalUI(console=Console(file=io.StringIO(), width=80, height=30, theme=theme.THEME),
                          input_fn=lambda: next(answers))
        store = Mock()
        store.get.side_effect = lambda key, default=None: default
        app = Application(view, store=store)
        initial = [(COURSE, {'id': 'a', 'name': 'A', '_completion_status': 'not_started'}, 1),
                   (COURSE, {'id': 'b', 'name': 'B', '_completion_status': 'not_started'}, 1)]
        refreshed = [(COURSE, dict(initial[0][1], _completion_status='submitted'), 1), initial[1]]
        from unittest.mock import patch
        state = {}
        with patch.object(app, 'task_catalog', side_effect=[initial, refreshed]):
            with self.assertRaises(Cancelled):
                CourseWorkspace(app).tasks([COURSE], 3, state)
        self.assertEqual([item['id'] for _, item, _ in state['selected']], ['a', 'b'])
        self.assertEqual(state['selected'][0][1]['_completion_status'], 'submitted')


if __name__ == '__main__':
    unittest.main()
