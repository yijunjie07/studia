"""Check the real terminal screen, including CJK cell widths and scrolling."""
import unittest
from unittest.mock import patch

from prompt_toolkit.application import Application
from prompt_toolkit.data_structures import Size
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from prompt_toolkit.utils import get_cwidth

import checklist


class SizedOutput(DummyOutput):
    def __init__(self, columns):
        self.columns = columns

    def get_size(self):
        return Size(rows=18, columns=self.columns)


def render(rows, columns, *, extra_headers=(), cursor=1, keys='q'):
    screens = []

    def application(*args, **kwargs):
        def capture(app):
            screen = app.renderer.last_rendered_screen
            if screen:
                screens.append([
                    ''.join(screen.data_buffer[y][x].char for x in range(columns)).rstrip()
                    for y in range(18)
                ])
        return Application(*args, **kwargs, after_render=capture)

    with create_pipe_input() as pipe, patch('checklist.Application', side_effect=application):
        pipe.send_text(keys)
        result = checklist.choose_many('选择任务', rows, cursor=cursor,
                                       extra_headers=extra_headers,
                                       input=pipe, output=SizedOutput(columns))
    return screens[0], result


def cell_position(line, value):
    return get_cwidth(line[:line.index(value)])


class ChecklistLayoutTests(unittest.TestCase):
    def test_headers_and_mixed_length_values_share_fixed_columns(self):
        rows = [
            ('中文标题很长' * 10, '已提交', '作业', '99.5', '9999'),
            ('短标题', '未作答', '考试', '?', '?'),
            ('其他任务', '已提交', '作业', '--', '不限'),
        ]
        for columns in (52, 80, 120):
            with self.subTest(columns=columns):
                screen, _ = render(rows, columns, extra_headers=('成绩', '剩余次数'))
                headers = [line for line in screen if '名称' in line and '状态' in line]
                self.assertEqual(len(headers), 1, screen)
                header = headers[0]
                data = [line for line in screen if '已提交' in line or '未作答' in line]
                self.assertEqual(len(data), 3)
                for line, row in zip(data, rows):
                    for name, value in zip(('状态', '成绩', '剩余', '类型'),
                                           (row[1], row[3], row[4], row[2])):
                        # Two unknown values occupy separate metric cells.
                        start = cell_position(header, name)
                        positions = [get_cwidth(line[:i]) for i in range(len(line))
                                     if line.startswith(value, i)]
                        self.assertIn(start, positions, line)
                    self.assertLessEqual(get_cwidth(line), columns)
                self.assertGreaterEqual(cell_position(header, '状态') - 6, 12)
                self.assertTrue(any('All 全选' in line for line in screen))

    def test_header_remains_visible_when_list_scrolls_and_cursor_keeps_row_index(self):
        rows = [(f'任务{i}', '未作答', '作业', '?', '?') for i in range(40)]
        screen, result = render(rows, 52, extra_headers=('成绩', '剩余次数'),
                                cursor=40, keys=' \r')
        self.assertTrue(any('名称' in line and '成绩' in line for line in screen), screen)
        self.assertTrue(any('任务39' in line for line in screen), screen)
        self.assertEqual(result.indexes, [39])
        self.assertEqual(result.cursor, 40)

    def test_course_list_omits_empty_task_status_and_metric_columns(self):
        screen, result = render([('中文课程', '', '课程介绍'), ('第二门课', '', '另一段介绍')],
                                52, cursor=0, keys=' \r')
        headers = [line for line in screen if '名称' in line]
        self.assertEqual(len(headers), 1, screen)
        self.assertIn('详情', headers[0])
        self.assertNotIn('状态', headers[0])
        self.assertNotIn('成绩', headers[0])
        self.assertEqual(result.indexes, [0, 1])


if __name__ == '__main__':
    unittest.main()
