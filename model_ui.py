"""Model picker and draft editor. Never writes credentials or contacts a service."""
from dataclasses import dataclass
from typing import Optional

from prompt_toolkit.application import Application, get_app
from prompt_toolkit.filters import has_focus
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.bindings.focus import focus_next, focus_previous
from prompt_toolkit.layout import HSplit, VSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.containers import DynamicContainer
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import TextArea, Button, Label

from ai.client import AIConfig
from checklist import fit


STYLE = Style.from_dict({
    'title': 'ansicyan bold', 'active': 'ansicyan bold',
    'cursor': 'bg:ansicyan ansiblack bold', 'error': 'ansiyellow',
    'text-area': 'bg:#202b33 #ffffff', 'text-area focused': 'bg:#263b45 #ffffff',
    'button': 'ansicyan', 'button.focused': 'bg:ansicyan ansiblack bold',
})


@dataclass
class ModelChoice:
    action: str
    profile_id: Optional[str] = None


@dataclass
class ModelEdit:
    action: str
    config: Optional[AIConfig] = None


def choose_model(rows, active_id=None, *, cursor_id=None, message='', locked_ids=(), input=None, output=None):
    """Rows contain only (id, provider, model, status), never API keys."""
    cursor = next((i for i, row in enumerate(rows) if row[0] == (cursor_id or active_id)), 0)
    keys = KeyBindings()

    @keys.add('up')
    def up(event):
        nonlocal cursor
        cursor = max(0, cursor - 1)

    @keys.add('down')
    def down(event):
        nonlocal cursor
        cursor = min(len(rows), cursor + 1)

    @keys.add('enter')
    def select(event):
        event.app.exit(result=ModelChoice('select', rows[cursor][0]) if cursor < len(rows)
                       else ModelChoice('add'))

    @keys.add('e')
    def edit(event):
        if cursor < len(rows) and rows[cursor][0] not in locked_ids:
            event.app.exit(result=ModelChoice('edit', rows[cursor][0]))

    @keys.add('escape')
    @keys.add('b')
    @keys.add('c-c')
    @keys.add('c-d')
    def back(event):
        event.app.exit(result=ModelChoice('back'))

    def content():
        width = max(12, app.output.get_size().columns - 2)
        name_width = max(5, (width - 5) // 3)
        status_width = min(10, max(4, width // 5))
        model_width = max(1, width - name_width - status_width - 9)
        result = []
        for i in range(len(rows) + 1):
            focused = i == cursor
            style = 'class:cursor' if focused else 'class:active' if i < len(rows) and rows[i][0] == active_id else ''
            if focused:
                result.append(('[SetCursorPosition]', ''))
            if i == len(rows):
                line = '  ＋ 添加模型'
            else:
                profile_id, provider, model, status = rows[i]
                line = ('› ' if focused else '  ') + ('● ' if profile_id == active_id else '○ ')
                line += fit(provider, name_width) + '  ' + fit(model, model_width) + '  ' + fit(status, status_width)
            result.append((style, fit(line, width)))
            if i < len(rows):
                result.append(('', '\n'))
        return result

    body = Window(FormattedTextControl(content, focusable=True), always_hide_cursor=True,
                  dont_extend_height=True, wrap_lines=False)
    app = Application(layout=Layout(HSplit([
        Label('选择模型', style='class:title'), Label('● 当前使用'), body,
        Label('↑↓ 选择 · 回车使用 · e 编辑自定义模型 · Esc 返回'),
        Label(message, style='class:error'),
    ]), focused_element=body), key_bindings=keys, style=STYLE, full_screen=True,
        input=input, output=output)
    try:
        return app.run()
    except EOFError:
        return ModelChoice('back')


def draft_config(url, model, key, current=None, *, provider_name=""):
    """Blank keys reuse only the original normalized service URL."""
    if not key.strip() and current:
        if url.strip().rstrip('/') != current.base_url:
            raise ValueError('接口地址已更改，请填写新 API Key')
        key = current.api_key
    return AIConfig(url, model, key, provider_name=provider_name)


def edit_model(current=None, *, input=None, output=None):
    provider = TextArea(text=current.provider_name if current else '', multiline=False)
    url = TextArea(text=current.base_url if current else '', multiline=False)
    model = TextArea(text=current.model if current else '', multiline=False)
    key = TextArea(text='', multiline=False, password=True)
    error = ''
    keys = KeyBindings()

    def finish(action):
        app.exit(result=ModelEdit(action))

    def save():
        nonlocal error
        try:
            config = draft_config(url.text, model.text, key.text, current, provider_name=provider.text)
        except ValueError as exc:
            error = str(exc)
            return
        app.exit(result=ModelEdit('save', config))

    save_button = Button('保存并测试', handler=save, width=16)
    buttons = [save_button, Button('取消', handler=lambda: finish('back'))]
    if current:
        buttons.append(Button('删除', handler=lambda: finish('delete')))
    button_row = VSplit(buttons, padding=2)
    button_column = HSplit(buttons)
    responsive_buttons = DynamicContainer(lambda: button_column
        if get_app().output.get_size().columns < (44 if current else 30) else button_row)

    keys.add('tab')(focus_next)
    keys.add('s-tab')(focus_previous)

    @keys.add('enter', filter=has_focus(provider) | has_focus(url) | has_focus(model) | has_focus(key))
    def next_field(event):
        event.app.layout.focus_next()

    @keys.add('escape')
    @keys.add('c-c')
    @keys.add('c-d')
    def cancel(event):
        finish('back')

    app = Application(layout=Layout(HSplit([
        Label('编辑模型' if current else '添加模型', style='class:title'),
        Label('供应商名称（可留空）'), provider,
        Label('接口地址（OpenAI 兼容 · 含 /v1 等路径）'), url,
        Label('模型名称（Model ID）'), model,
        Label('API Key · 已设置，留空保留' if current else 'API Key'), key,
        Window(height=1), responsive_buttons,
        Label('Tab 下一项 · Shift+Tab 上一项 · Esc 返回'),
        Window(FormattedTextControl(lambda: [('class:error', error)]), height=2, wrap_lines=True),
    ]), focused_element=provider), key_bindings=keys, style=STYLE, full_screen=True,
        input=input, output=output)
    try:
        return app.run()
    except EOFError:
        return ModelEdit('back')
