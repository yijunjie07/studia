import io
import unittest

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from prompt_toolkit.output.vt100 import Vt100_Output
from prompt_toolkit.output import ColorDepth
from prompt_toolkit.data_structures import Size

from ai.client import AIConfig


class ModelUITests(unittest.TestCase):
    def picker(self, keys, active='a', rows=None):
        from model_ui import choose_model
        rows = rows if rows is not None else [('a', '供应商一', 'same', '✓'),
                                              ('b', '供应商二', 'same', '?')]
        with create_pipe_input() as pipe:
            pipe.send_text(keys)
            return choose_model(rows, active, input=pipe, output=DummyOutput())

    def form(self, keys, current=None):
        from model_ui import edit_model
        with create_pipe_input() as pipe:
            pipe.send_text(keys)
            return edit_model(current, input=pipe, output=DummyOutput())

    def test_four_fields_save_without_protocol_selection_and_preserve_detected_format(self):
        old = AIConfig('https://one.example/v1', 'old', 'secret-key', api_format='responses')
        result = self.form('供应商\t\t\t\t\r\x03', old)
        self.assertEqual(result.action, 'save')
        self.assertEqual(result.config.provider_name, '供应商')
        self.assertEqual(result.config.api_format, 'responses')
        self.assertEqual(result.config.api_key, 'secret-key')
        self.assertEqual(old.provider_name, '')

    def test_draft_retains_detected_format_only_when_connection_fields_are_unchanged(self):
        from model_ui import draft_config
        old = AIConfig('https://one.example/v1', 'old', 'secret-key', api_format='responses')
        renamed = draft_config(' https://one.example/v1/ ', ' old ', '', old, provider_name='新名称')
        self.assertEqual(renamed.api_format, 'responses')
        self.assertEqual(renamed.api_key, 'secret-key')
        for url, model, key in [('https://one.example/v1', 'new', ''),
                                ('https://one.example/v1', 'old', 'new-key'),
                                ('https://two.example/v1', 'old', 'new-key')]:
            with self.subTest(url=url, model=model):
                updated = draft_config(url, model, key, old)
                self.assertEqual(updated.api_format, 'auto')
        with self.assertRaisesRegex(ValueError, '新 API Key'):
            draft_config('https://two.example/v1', 'new', '', old)

    def test_new_draft_uses_auto_but_complete_endpoint_specifies_format(self):
        from model_ui import draft_config
        self.assertEqual(draft_config('https://one.example/v1', 'model', 'key').api_format, 'auto')
        self.assertEqual(draft_config('https://one.example/v1/responses', 'model', 'key').api_format,
                         'responses')

    def test_provider_name_is_independent_from_connection_fields_and_cancel_discards_it(self):
        result = self.form('  我的供应商  \thttps://two.example/v1\tmodel-b\tnew-key\t\r')
        self.assertEqual(result.action, 'save')
        self.assertEqual(result.config.provider_name, '我的供应商')
        self.assertEqual(result.config.base_url, 'https://two.example/v1')
        old = result.config
        cancelled = self.form('changed\x1b', old)
        self.assertEqual(cancelled.action, 'back')
        self.assertIsNone(cancelled.config)
        self.assertEqual(old.provider_name, '我的供应商')
        renamed = self.form('\x01\x0b新名称\t\t\t\t\r', old)
        self.assertEqual(renamed.config.provider_name, '新名称')
        self.assertEqual(renamed.config.base_url, old.base_url)
        self.assertEqual(renamed.config.model, old.model)
        self.assertEqual(renamed.config.api_key, old.api_key)
        self.assertEqual(old.provider_name, '我的供应商')

    def test_enter_switches_only_highlighted_profile_and_keeps_active_initial_cursor(self):
        self.assertEqual(self.picker('\x1b[B\r').profile_id, 'b')
        self.assertEqual(self.picker('\r', active='b').profile_id, 'b')

    def test_add_row_edit_and_escape_are_distinct_actions(self):
        self.assertEqual(self.picker('\x1b[B\x1b[B\r').action, 'add')
        result = self.picker('\x1b[Be')
        self.assertEqual((result.action, result.profile_id), ('edit', 'b'))
        self.assertEqual(self.picker('\x1b').action, 'back')
        self.assertEqual(self.picker('\r', rows=[]).action, 'add')

    def test_default_picker_ignores_edit_but_still_allows_selection(self):
        from model_ui import choose_model
        rows = [('builtin-default', '默认供应商', 'shared-model', '?'), ('custom', '自定义供应商', 'same', '?')]
        for keys, expected in (('e\r', ('select', 'builtin-default')),
                               ('e\x1b[Be', ('edit', 'custom'))):
            with self.subTest(keys=keys), create_pipe_input() as pipe:
                pipe.send_text(keys)
                result = choose_model(rows, 'builtin-default', locked_ids={'builtin-default'},
                                      input=pipe, output=DummyOutput())
                self.assertEqual((result.action, result.profile_id), expected)

    def test_form_tabs_edit_model_and_blank_key_reuses_same_service(self):
        old = AIConfig('https://one.example/v1', 'old', 'secret-key')
        result = self.form('\t\t\x01\x0bnew-model\t\t\r', old)
        self.assertEqual(result.action, 'save')
        self.assertEqual(result.config.model, 'new-model')
        self.assertEqual(result.config.api_key, 'secret-key')
        self.assertEqual(old.model, 'old')

    def test_new_configuration_and_cancel_dont_share_mutable_state(self):
        result = self.form('\thttps://two.example/v1\tmodel-b\tnew-key\t\r')
        self.assertEqual(result.config, AIConfig('https://two.example/v1', 'model-b', 'new-key'))
        old = AIConfig('https://one.example/v1', 'old', 'secret-key')
        result = self.form('\t\x01\x0bhttps://changed.example/v1\x1b', old)
        self.assertEqual(result.action, 'back')
        self.assertIsNone(result.config)
        self.assertEqual(old.base_url, 'https://one.example/v1')

    def test_changed_service_requires_new_key_and_preserves_typed_fields_on_error(self):
        old = AIConfig('https://one.example/v1', 'old', 'secret-key')
        result = self.form('\t\x01\x0bhttps://two.example/v1\t\t\t\r\x1b[Znew-key\t\r', old)
        self.assertEqual(result.config.base_url, 'https://two.example/v1')
        self.assertEqual(result.config.api_key, 'new-key')

    def test_delete_exists_only_in_edit_form(self):
        old = AIConfig('https://one.example/v1', 'old', 'secret-key')
        self.assertEqual(self.form('\t\t\t\t\t\t\r', old).action, 'delete')
        self.assertEqual(self.form('\t\t\t\t\t\r').action, 'back')

    def test_passwords_are_masked_in_real_terminal_rendering(self):
        from model_ui import edit_model
        old = AIConfig('https://one.example/v1', 'old', 'old-private-key')
        for width in (40, 52, 80):
            with self.subTest(width=width), create_pipe_input() as pipe:
                stream = io.StringIO()
                output = Vt100_Output(stream, lambda: Size(rows=24, columns=width),
                                      term='xterm-256color', default_color_depth=ColorDepth.DEPTH_8_BIT,
                                      enable_cpr=False)
                pipe.send_text('\t\t\tnew-private-key\t\r\x03')
                result = edit_model(old, input=pipe, output=output)
                self.assertEqual(result.action, 'save')
                self.assertEqual(result.config.api_key, 'new-private-key')
                self.assertNotIn('old-private-key', stream.getvalue())
                self.assertNotIn('new-private-key', stream.getvalue())
                self.assertIn('保存并测试', stream.getvalue())
                self.assertNotIn('Window too small', stream.getvalue())
