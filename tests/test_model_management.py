import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rich.console import Console
import theme

from ai.client import AIConfig, AIError
from app import Application
from course_flow import CourseWorkspace
from model_ui import ModelChoice, ModelEdit
from settings import SettingsStore, SettingsError
from ui import TerminalUI, Back


class ModelManagementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SettingsStore(Path(self.temp.name))
        default_patch = patch('ai.defaults.default_config', return_value=AIConfig(
            'https://mochif.com/v1', 'gemini-3.8-flash', 'test-shared-key'))
        default_patch.start()
        self.addCleanup(default_patch.stop)
        self.output = io.StringIO()
        self.view = TerminalUI(console=Console(file=self.output, theme=theme.THEME))
        self.app = Application(self.view, self.store)
        self.a = AIConfig('https://one.example/v1', 'first', 'key-one')
        self.b = AIConfig('https://two.example/v1', 'second', 'key-two')

    def test_custom_provider_name_is_shown_in_picker_and_answer_summary(self):
        config = AIConfig('https://private.example/v1', 'same-model', 'private-key',
                          provider_name='课程供应商')
        self.store.save_ai_profile(config)
        self.view.input_fn = lambda: 'b'
        self.app.manage_models()
        self.view.input_fn = lambda: ''
        self.view.review_ai([], config, {})
        rendered = self.output.getvalue()
        self.assertGreaterEqual(rendered.count('课程供应商'), 2)
        self.assertIn('same-model', rendered)
        self.assertNotIn('private.example', rendered)
        self.assertNotIn('private-key', rendered)

    def test_default_picker_hides_provider_url_and_blocks_editor(self):
        self.store.save_ai_profile(self.a)
        self.store.ensure_default_model()
        default = next(p for p in self.store.ai_profiles() if p.config.model == 'gemini-3.8-flash')
        inputs = iter(['e 1', 'b'])
        self.view.input_fn = lambda: next(inputs)
        with patch.object(self.view, 'model_editor', side_effect=AssertionError('default editor must not open')):
            self.assertEqual(self.app.manage_models(), self.a)
        rendered = self.output.getvalue()
        self.assertIn('默认供应商', rendered)
        self.assertNotIn(default.config.base_url.split('://', 1)[-1], rendered)
        self.assertNotIn(default.config.api_key, rendered)
        self.assertIn('自定义供应商', rendered)
        self.assertIn('gemini-3.8-flash', rendered)
        self.assertNotIn('one.example/v1', rendered)
        self.assertLess(rendered.index('默认供应商'), rendered.index('自定义供应商'))

    def test_application_rejects_default_edit_even_if_picker_requests_it(self):
        self.store.ensure_default_model()
        default = self.store.ai_profiles()[0]
        before = self.store.path.read_bytes()
        with patch.object(self.view, 'model_picker', side_effect=[ModelChoice('edit', default.id), ModelChoice('back')]), \
             patch.object(self.view, 'model_editor', side_effect=AssertionError('default editor must not open')):
            self.assertEqual(self.app.manage_models(), default.config)
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertIn('默认供应商', self.output.getvalue())

    def test_add_saves_tests_and_reuses_without_reentering_credentials(self):
        with patch.object(self.view, 'model_picker', side_effect=[ModelChoice('add'), ModelChoice('back')]), \
             patch.object(self.view, 'model_editor', return_value=ModelEdit('save', self.a)), \
             patch('app.AIClient.check_connection', return_value=None):
            self.assertEqual(self.app.ai_configuration(), self.a)
        self.assertEqual(self.store.ai_health(self.a)['status'], 'ok')
        self.assertEqual(Application(self.view, SettingsStore(self.store.directory)).ai_configuration(), self.a)
        self.assertNotIn('key-one', self.output.getvalue())

    def test_failed_test_keeps_new_profile_without_overwriting_current(self):
        self.store.save_ai_profile(self.a)
        with patch.object(self.view, 'model_picker', side_effect=[ModelChoice('add'), ModelChoice('back')]), \
             patch.object(self.view, 'model_editor', return_value=ModelEdit('save', self.b)), \
             patch('app.AIClient.check_connection', side_effect=AIError('网络超时')):
            self.assertEqual(self.app.manage_models(), self.a)
        self.assertEqual(len(self.store.ai_profiles()), 2)
        self.assertEqual(self.store.ai_health(self.b)['status'], 'error')

    def test_cancel_editor_or_delete_confirmation_leaves_settings_identical(self):
        first = self.store.save_ai_profile(self.a)
        before = self.store.path.read_bytes()
        with patch.object(self.view, 'model_picker', side_effect=[ModelChoice('edit', first),
                          ModelChoice('edit', first), ModelChoice('back')]), \
             patch.object(self.view, 'model_editor', side_effect=[ModelEdit('back'), ModelEdit('delete')]), \
             patch.object(self.view, 'confirm', return_value=False):
            self.assertEqual(self.app.manage_models(), self.a)
        self.assertEqual(self.store.path.read_bytes(), before)

    def test_save_failure_does_not_test_or_activate_unsaved_configuration(self):
        first = self.store.save_ai_profile(self.a)
        with patch.object(self.view, 'model_picker', side_effect=[ModelChoice('edit', first), ModelChoice('back')]), \
             patch.object(self.view, 'model_editor', return_value=ModelEdit('save', self.b)), \
             patch.object(self.store, 'save_ai_profile', side_effect=SettingsError('磁盘已满')), \
             patch('app.AIClient.check_connection', side_effect=AssertionError('must not test unsaved model')):
            self.assertEqual(self.app.manage_models(), self.a)
        self.assertEqual(self.store.ai_config(), self.a)
        self.assertIn('磁盘已满', self.output.getvalue())

    def test_first_configuration_cancel_returns_without_answering(self):
        with patch.object(self.view, 'model_picker', return_value=ModelChoice('back')):
            with self.assertRaises(Back):
                self.app.ai_configuration()

    def test_switch_in_summary_tests_and_answers_new_model_with_same_tasks_and_options(self):
        self.store.save_ai_profile(self.a)
        second = self.store.save_ai_profile(self.b)
        selected = [({'id': 'ci', 'courseId': 'c'}, {'id': 'p', 'name': '试卷'}, 1)]
        inputs = iter(['s', '2', '.9', 'b', 'm', 't', ''])
        self.view.input_fn = lambda: next(inputs)
        state = {}
        seen = []

        def execute(client, tasks, config, auto_submit, threshold):
            seen.append((tasks, config, auto_submit, threshold))
            return []

        with patch.object(self.app, 'task_catalog', return_value=selected), \
             patch.object(self.view, 'papers', return_value=selected), \
             patch.object(self.view, 'model_picker', return_value=ModelChoice('select', second)), \
             patch('app.AIClient.check_connection', autospec=True, side_effect=lambda client: seen.append(client.config)), \
             patch.object(self.app, 'execute_ai', side_effect=execute), \
             patch.object(self.view, 'operation_result', return_value=1):
            CourseWorkspace(self.app).tasks([selected[0][0]], 3, state)
        self.assertEqual(seen, [self.b, (selected, self.b, True, .9)])
        self.assertEqual(self.store.ai_config(), self.b)
        self.assertIn('second', self.output.getvalue())

    def test_deleting_current_in_summary_blocks_start_until_a_model_is_selected(self):
        inputs = iter(['m', '', 'b'])
        self.view.input_fn = lambda: next(inputs)
        options = {}
        with self.assertRaises(Back):
            self.view.review_ai([], self.a, options, manage_models=lambda: None)
        self.assertIsNone(options['config'])
        self.assertIn('选择模型', self.output.getvalue())
