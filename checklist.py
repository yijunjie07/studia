"""Keyboard multiselect. Presentation only; never opens or executes a task."""
from dataclasses import dataclass
from typing import Optional

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style
from prompt_toolkit.utils import get_cwidth


@dataclass
class Selection:
    indexes: list
    cursor: int
    action: Optional[str] = None


def fit(text, width):
    """One physical row, accounting for Chinese full-width characters."""
    text = str(text).replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
    text = ''.join(c for c in text if ord(c) >= 32 and ord(c) != 127)
    if get_cwidth(text) <= width:
        return text + ' ' * (width - get_cwidth(text))
    value = ''
    for char in text:
        if get_cwidth(value + char) > max(0, width - 1):
            break
        value += char
    return value + '…' + ' ' * max(0, width - get_cwidth(value) - 1)


def choose_many(title, rows, *, selected=(), cursor=1, refresh=False, heading='',
                extra_headers=(), input=None, output=None):
    """Rows are (label, status, detail, *extras); indexes refer to original rows."""
    checked = {i for i in selected if 0 <= i < len(rows)}
    cursor = min(max(0, cursor), len(rows))
    message = ''
    keys = KeyBindings()

    def finish(event, action=None):
        event.app.exit(result=Selection(sorted(checked), cursor, action))

    @keys.add('up')
    def up(event):
        nonlocal cursor
        cursor = max(0, cursor - 1)

    @keys.add('down')
    def down(event):
        nonlocal cursor
        cursor = min(len(rows), cursor + 1)

    @keys.add(' ')
    def toggle(event):
        nonlocal message
        message = ''
        if cursor == 0:
            if len(checked) == len(rows):
                checked.clear()
            else:
                checked.update(range(len(rows)))
        elif cursor - 1 in checked:
            checked.remove(cursor - 1)
        else:
            checked.add(cursor - 1)

    @keys.add('enter')
    def confirm(event):
        nonlocal message
        if checked:
            finish(event)
        else:
            message = '请先用空格选择任务。'

    @keys.add('escape')
    @keys.add('b')
    def back(event):
        finish(event, 'back')

    @keys.add('q')
    @keys.add('c-c')
    @keys.add('c-d')
    def quit(event):
        finish(event, 'quit')

    if refresh:
        @keys.add('r')
        def reload(event):
            finish(event, 'r')

    def header():
        text = (heading + '\n\n') if heading else ''
        return [('class:title', text + f'{title}  ·  已选 {len(checked)}/{len(rows)} 项\n')]

    def columns():
        """Use one set of terminal-cell widths for the entire list and its header."""
        terminal_width = app.output.get_size().columns
        width = max(1, terminal_width - 2)
        task_rows = any(row[1] for row in rows) or bool(extra_headers)
        fields = []
        if task_rows:
            fields.append(('状态', 1, 10))
        for index, name in enumerate(extra_headers, 3):
            if name == '成绩':
                name = '成绩(分)' if terminal_width >= 80 else '成绩'
            elif name in ('剩余次数', '剩余'):
                name = '剩余(次)' if terminal_width >= 80 else '剩余'
            fields.append((name, index, 10))
        if task_rows or any(row[2] for row in rows):
            fields.append(('类型' if task_rows else '详情', 2, min(24, width // 4)))
        widths = [max(get_cwidth(name), min(limit, max(
            (get_cwidth(str(row[index])) for row in rows if index < len(row)), default=0)))
            for name, index, limit in fields]
        # Preserve useful name space even with long metadata in a narrow terminal.
        metadata_budget = max(0, width - 6 - 12 - 2 * len(fields))
        while sum(widths) > metadata_budget and any(size > 2 for size in widths):
            largest = max(range(len(widths)), key=widths.__getitem__)
            widths[largest] -= 1
        name_width = max(1, width - 6 - sum(widths) - 2 * len(fields))
        return width, [('名称', 0, name_width)] + [
            (name, index, size) for (name, index, _), size in zip(fields, widths)]

    def column_header():
        width, fields = columns()
        line = ' ' * 6 + '  '.join(fit(name, size) for name, _, size in fields)
        return [('class:columns', fit(line, width))]

    def content():
        width, fields = columns()
        all_mark = 'x' if rows and len(checked) == len(rows) else '-' if checked else ' '
        all_label = 'All 取消全选' if rows and len(checked) == len(rows) else 'All 全选'
        display = [(all_mark, all_label, '', '')]
        display += [('x' if i in checked else ' ', *row) for i, row in enumerate(rows)]
        fragments = []
        for index, (mark, *values) in enumerate(display):
            active = index == cursor
            style = 'class:cursor' if active else 'class:checked' if mark == 'x' else ''
            if active:
                fragments.append(('[SetCursorPosition]', ''))
            prefix = ('> ' if active else '  ') + f'[{mark}] '
            line = prefix + '  '.join(
                fit(values[column] if column < len(values) else '', size)
                for _, column, size in fields)
            fragments.append((style, fit(line, width)))
            if index < len(display) - 1:
                fragments.append(('', '\n'))
        return fragments

    def footer():
        hint = '↑↓ 移动 · 空格 勾选/取消 · Enter 确认\nEsc 返回 · q 退出'
        if refresh:
            hint += ' · r 刷新状态'
        return [('', '\n' + hint), ('class:warning', '\n' + message if message else '')]

    body = Window(FormattedTextControl(content, focusable=True), wrap_lines=False,
                  always_hide_cursor=True, dont_extend_height=True)
    app = Application(layout=Layout(HSplit([
        Window(FormattedTextControl(header), dont_extend_height=True),
        Window(FormattedTextControl(column_header), height=1, wrap_lines=False),
        body,
        Window(FormattedTextControl(footer), dont_extend_height=True, wrap_lines=True),
    ]), focused_element=body), key_bindings=keys, full_screen=True,
        style=Style.from_dict({'title': 'ansicyan bold', 'columns': 'bold', 'checked': 'ansicyan bold',
                               'cursor': 'bg:ansicyan ansiblack bold', 'warning': 'ansiyellow'}),
        input=input, output=output)
    try:
        return app.run()
    except EOFError:
        return Selection(sorted(checked), cursor, 'quit')
