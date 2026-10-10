"""Resource progress and disabled task selection at real terminal boundaries."""
import io
import unittest
from functools import partial
from unittest.mock import patch

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from rich.console import Console

import theme
from checklist import choose_many
from reporting import ProgressEvent
from ui import TerminalUI


class ResourceBarTests(unittest.TestCase):
    def view(self):
        out = io.StringIO()
        return TerminalUI(console=Console(file=out, width=140, theme=theme.THEME)), out

    def test_resources_show_fraction_percentage_without_completing_course(self):
        view, out = self.view()
        view.on_progress(ProgressEvent('begin', '学习管理', total=1, unit='门课程'))
        view.on_progress(ProgressEvent('resources', '成功 1 · 跳过 0 · 失败 0', total=4, completed=1))
        view.console.print(view.render())
        self.assertIn('1/4', out.getvalue())
        self.assertIn('25%', out.getvalue())
        self.assertIn('成功 1', out.getvalue())
        self.assertEqual(view.progress.tasks[0].completed, 0)
        self.assertFalse(view.counts)

    def test_next_course_and_next_operation_clear_previous_total(self):
        view, out = self.view()
        view.on_progress(ProgressEvent('resources', '已处理', total=9, completed=9))
        view.on_progress(ProgressEvent('resources', '读取当前课程资源', completed=0))
        view.console.print(view.render())
        self.assertIn('0/?', out.getvalue())
        self.assertNotIn('9/9', out.getvalue())
        out.seek(0)
        out.truncate()
        view.begin_operation()
        view.console.print(view.render())
        self.assertNotIn('读取当前课程资源', out.getvalue())

    def test_long_resource_names_do_not_hide_outcome_counts_in_narrow_terminal(self):
        out = io.StringIO()
        view = TerminalUI(console=Console(file=out, width=52, theme=theme.THEME))
        view.on_progress(ProgressEvent('resources',
            '大学生心理健康教育 · 心理健康绪论教学视频 · 成功 12 · 跳过 3 · 失败 1',
            total=48, completed=16))
        view.console.print(view.render())
        for label in ('本课资源', '16/48', '33%', '成功 12', '跳过 3', '失败 1'):
            self.assertIn(label, out.getvalue())


class DisabledChecklistTests(unittest.TestCase):
    def test_papers_pass_attachment_restriction_to_native_checklist(self):
        course = {'id': 'course', 'courseName': '课程'}
        catalog = [(course, {'id': 'attachment', 'typeId': 3, 'name': '项目计划书'}, 1),
                   (course, {'id': 'normal', 'typeId': 1, 'name': '普通作业'}, 1)]
        view = TerminalUI(console=Console(file=io.StringIO(), force_terminal=True, theme=theme.THEME))
        with create_pipe_input() as pipe:
            pipe.send_text('\x1b[A \r')
            native = partial(choose_many, input=pipe, output=DummyOutput())
            with patch('checklist.choose_many', side_effect=native), patch('sys.stdin.isatty', return_value=True):
                self.assertEqual(view.papers(catalog), [catalog[1]])

    def choose(self, keys, disabled, selected=()):
        with create_pipe_input() as pipe:
            pipe.send_text(keys)
            return choose_many('任务', [('附件', '暂不支持', '附件作业'),
                                        ('普通', '未作答', '作业'),
                                        ('测验', '未作答', '测验')],
                               disabled=disabled, selected=selected,
                               input=pipe, output=DummyOutput())

    def test_all_excludes_disabled_and_clears_only_selectable_rows(self):
        self.assertEqual(self.choose('\x1b[A \r', {0}).indexes, [1, 2])
        self.assertEqual(self.choose('\x1b[A \x1b[B\x1b[B \r', {0}, (0, 1, 2)).indexes, [1])

    def test_space_cannot_select_disabled_and_stale_selection_is_removed(self):
        self.assertEqual(self.choose(' \x1b[B \r', {0}, (0,)).indexes, [1])

    def test_all_disabled_cannot_confirm_and_can_return(self):
        result = self.choose('\x1b[A \r\x1b', {0, 1, 2}, (0, 1, 2))
        self.assertEqual(result.indexes, [])
        self.assertEqual(result.action, 'back')
