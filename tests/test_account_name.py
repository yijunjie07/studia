"""Account identity follows authenticated sessions and fits the shortcut row."""
import io
import tempfile
import unittest
from unittest.mock import Mock, patch

from rich.cells import cell_len
from rich.console import Console

import theme
from app import Application
from course_flow import CourseWorkspace
from settings import SettingsStore
from ui import TerminalUI
from ZYKMoocMain.api import ZYKMoocApi


class AccountNameTests(unittest.TestCase):
    def view(self, width=80):
        out = io.StringIO()
        return TerminalUI(console=Console(file=out, width=width, theme=theme.THEME)), out

    def test_shortcut_row_right_aligns_name_without_extra_line(self):
        view, out = self.view()
        view.set_user({'displayName': '张三'})
        view.shortcuts('Esc 返回课程列表 · q 退出')
        lines = out.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].endswith('张三'))
        self.assertEqual(cell_len(lines[0]), 80)
        self.assertTrue(lines[0].startswith('Esc 返回课程列表 · q 退出'))

    def test_course_list_shows_name_once_across_both_shortcut_rows(self):
        view, out = self.view(120)
        view.input_fn = lambda: '1'
        view.set_user({'displayName': '张三'})
        course = {'id': 'c', 'courseName': '测试课程'}
        self.assertEqual(view.library([course], 0, {}), [course])
        self.assertEqual(out.getvalue().count('张三'), 1)
        name_line = next(line for line in out.getvalue().splitlines() if '张三' in line)
        self.assertIn('编号进入', name_line)

    def test_missing_name_never_displays_login_identifier_or_previous_name(self):
        view, out = self.view()
        view.set_user({'nickName': '李四'})
        view.set_user({'userName': '13800000000', 'userId': 'secret-id'})
        view.shortcuts('Esc 返回')
        self.assertEqual(out.getvalue().strip(), 'Esc 返回')

    def test_long_or_control_char_names_do_not_wrap_or_hide_controls(self):
        for width in (28, 40):
            with self.subTest(width=width):
                view, out = self.view(width)
                view.set_user({'displayName': '\x1b[31m张三\n' * 20})
                view.shortcuts('Esc 返回课程列表 · q 退出')
                lines = out.getvalue().splitlines()
                self.assertEqual(len(lines), 1)
                self.assertIn('Esc 返回课程列表 · q 退出', lines[0])
                self.assertLessEqual(cell_len(lines[0]), width)
                self.assertNotIn('\x1b', lines[0])

    def test_login_restore_sets_name_and_failed_refresh_clears_it(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(directory)
            store.save_session('mooc', Mock(access_token='token'))
            view, out = self.view()
            app = Application(view, store)
            client = Mock(access_token='token', user_info={'displayName': '王五'})
            client.my_course_list.return_value = {'rows': []}
            with patch('app.AIMoocApi', return_value=client):
                import app as module
                app.client_and_courses(module.AIMoocApi, choose=False)
                view.shortcuts('Esc 返回')
                self.assertIn('王五', out.getvalue())
                client.my_course_list.side_effect = RuntimeError('network')
                with self.assertRaises(RuntimeError):
                    app.client_and_courses(module.AIMoocApi, choose=False)
            out.seek(0)
            out.truncate()
            view.shortcuts('Esc 返回')
            self.assertNotIn('王五', out.getvalue())

    def test_switch_refresh_and_logout_clear_name(self):
        view, out = self.view()
        app = Application(view, Mock())
        workspace = CourseWorkspace(app)
        for action in ('t', 'r', 's'):
            view.set_user({'displayName': '旧账号'})
            workspace.platform = 0
            with patch.object(view, 'choose_platform', return_value=1), \
                 patch.object(app, 'manage_settings', return_value=True):
                workspace.root_action(action)
            out.seek(0)
            out.truncate()
            view.shortcuts('Esc 返回')
            self.assertNotIn('旧账号', out.getvalue())

    def test_resource_platform_keeps_authenticated_display_name(self):
        with patch('ZYKMoocMain.api.authenticated_get', return_value={
                'user': {'userId': 'user', 'nickName': '赵六'}}):
            client = ZYKMoocApi(access_token='synthetic-token')
        self.assertEqual(client.user_info['nickName'], '赵六')
