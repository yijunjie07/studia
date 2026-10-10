import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ai.client import AIConfig
from app import Application
from settings import SettingsStore, SettingsError


class ModelProfilesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SettingsStore(Path(self.temp.name))
        default_patch = patch('ai.defaults.default_config', return_value=AIConfig(
            'https://mochif.com/v1', 'gemini-3.8-flash', 'test-shared-key'))
        default_patch.start()
        self.addCleanup(default_patch.stop)
        self.a = AIConfig('https://one.example/v1', 'same-model', 'key-one')
        self.b = AIConfig('https://two.example/v1', 'same-model', 'key-two')

    def test_provider_name_round_trip_and_rename_preserve_connection_health(self):
        named = AIConfig(self.a.base_url, self.a.model, self.a.api_key,
                         provider_name='  我的供应商  ')
        profile_id = self.store.save_ai_profile(named)
        self.store.save_ai_health(named, 'ok')
        named.provider_name = '另一个名称'
        self.store.save_ai_profile(named, profile_id)
        restarted = SettingsStore(self.store.directory)
        self.assertEqual(restarted.ai_config().provider_name, '另一个名称')
        self.assertEqual(restarted.ai_health(named)['status'], 'ok')

    def test_legacy_name_is_optional_and_default_name_is_fixed(self):
        self.store.set('ai', {'base_url': self.a.base_url, 'model': self.a.model,
                              'api_key': self.a.api_key})
        self.assertEqual(self.store.ai_config().provider_name, '')
        self.store.ensure_default_model()
        self.assertEqual(self.store.ai_profiles()[0].config.provider_name, '默认供应商')

    def test_default_model_is_ready_on_first_start_and_not_duplicated(self):
        self.store.ensure_default_model()
        config = self.store.ai_config()
        self.assertIsNotNone(config)
        self.assertEqual(config.base_url, 'https://mochif.com/v1')
        self.assertEqual(config.model, 'gemini-3.8-flash')
        self.assertTrue(config.api_key)
        before = self.store.path.read_bytes()
        SettingsStore(self.store.directory).ensure_default_model()
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertEqual(len(self.store.ai_profiles()), 1)

    def test_app_initializes_default_before_opening_courses(self):
        def open_courses():
            self.assertIsNotNone(self.store.ai_config())
            return 'opened'
        with patch('course_flow.CourseWorkspace.run', side_effect=open_courses):
            self.assertEqual(Application(Mock(), self.store).run(), 'opened')

    def test_default_model_preserves_current_model_and_can_be_selected(self):
        self.store.save_ai_profile(self.a)
        self.store.save_ai_health(self.a, 'ok')
        self.store.ensure_default_model()
        self.assertEqual(self.store.ai_config(), self.a)
        self.assertEqual(self.store.ai_health(self.a)['status'], 'ok')
        shared = next(p for p in self.store.ai_profiles() if p.config.model == 'gemini-3.8-flash')
        self.store.activate_ai_profile(shared.id)
        self.assertEqual(SettingsStore(self.store.directory).ai_config(), shared.config)

    def test_default_model_is_locked_in_all_edit_and_delete_apis(self):
        self.store.ensure_default_model()
        profile = self.store.ai_profiles()[0]
        before = self.store.path.read_bytes()
        for operation in (lambda: self.store.save_ai_profile(self.a, profile.id),
                          lambda: self.store.save_ai(self.a),
                          lambda: self.store.delete_ai_profile(profile.id)):
            with self.subTest(operation=operation), self.assertRaisesRegex(SettingsError, '默认供应商'):
                operation()
            self.assertEqual(self.store.path.read_bytes(), before)
        self.assertTrue(profile.builtin)
        self.assertEqual(profile.id, 'builtin-default')

    def test_default_is_first_without_changing_custom_selection_or_editability(self):
        custom_id = self.store.save_ai_profile(self.a)
        self.store.ensure_default_model()
        self.assertTrue(self.store.ai_profiles()[0].builtin)
        self.assertFalse(self.store.ai_profiles()[1].builtin)
        self.store.save_ai_profile(self.b, custom_id)
        self.assertEqual(self.store.ai_config(), self.b)
        self.store.delete_ai_profile(custom_id)
        self.assertTrue(self.store.ai_profiles()[0].builtin)
        self.assertIsNone(self.store.ai_config())

    def test_old_default_is_migrated_without_duplicates_and_retains_health_and_selection(self):
        from ai.defaults import default_config
        shared = default_config()
        old_id = self.store.save_ai_profile(shared)
        self.store.save_ai_health(shared, 'ok')
        custom_id = self.store.save_ai_profile(self.a)
        self.store.set('default_model_added', True)
        self.store.ensure_default_model()
        profiles = self.store.ai_profiles()
        self.assertEqual([p.id for p in profiles], ['builtin-default', custom_id])
        self.assertNotEqual(profiles[0].id, old_id)
        self.assertTrue(profiles[0].builtin)
        self.assertTrue(profiles[0].active)
        self.assertEqual(self.store.ai_health(shared)['status'], 'ok')

    def test_previously_edited_default_is_preserved_as_custom_and_default_is_restored(self):
        old_id = self.store.save_ai_profile(self.a)
        self.store.set('default_model_added', True)
        self.store.ensure_default_model()
        self.assertEqual([p.id for p in self.store.ai_profiles()], ['builtin-default', old_id])
        self.assertEqual(self.store.ai_config(), self.a)

    def test_clear_ai_keeps_default_and_clears_only_custom_selection(self):
        self.store.ensure_default_model()
        builtin = self.store.ai_profiles()[0]
        custom_id = self.store.save_ai_profile(self.a)
        self.store.activate_ai_profile(custom_id)
        self.store.clear_ai()
        self.assertEqual([p.id for p in self.store.ai_profiles()], [builtin.id])
        self.assertIsNone(self.store.ai_config())
        self.store.activate_ai_profile(builtin.id)
        self.store.clear_ai()
        self.assertEqual(self.store.ai_config(), builtin.config)

    def test_legacy_migration_preserves_health_credentials_and_other_settings(self):
        self.store.set('ai', {'base_url': self.a.base_url, 'model': self.a.model, 'api_key': self.a.api_key})
        self.store.set('ai_health', {'config': self.store.ai_fingerprint(self.a), 'status': 'ok'})
        self.store.set('confidence', .9)
        before = self.store.path.read_bytes()
        profiles = self.store.ai_profiles()
        self.assertEqual(profiles[0].config, self.a)
        self.assertTrue(profiles[0].active)
        self.assertEqual(self.store.path.read_bytes(), before)
        self.store.save_ai_profile(self.b)
        restarted = SettingsStore(self.store.directory)
        self.assertEqual(restarted.ai_config(), self.a)
        self.assertEqual(restarted.ai_health(self.a)['status'], 'ok')
        self.assertEqual(restarted.get('confidence'), .9)
        self.assertIsNone(restarted.get('ai'))
        self.assertEqual(len(restarted.ai_profiles()), 2)

    def test_switch_and_edit_keep_other_profile_and_separate_health(self):
        first = self.store.save_ai_profile(self.a)
        second = self.store.save_ai_profile(self.b)
        self.store.save_ai_health(self.a, 'ok')
        self.store.save_ai_health(self.b, 'error', '连接失败')
        self.store.activate_ai_profile(second)
        self.assertEqual(SettingsStore(self.store.directory).ai_config(), self.b)
        changed = AIConfig(self.a.base_url, 'new-model', self.a.api_key)
        self.store.save_ai_profile(changed, first)
        self.assertEqual(self.store.ai_config(), self.b)
        self.assertEqual(self.store.ai_health(changed), {})
        self.assertEqual(self.store.ai_health(self.b)['status'], 'error')
        self.store.activate_ai_profile(first)
        self.assertEqual(self.store.ai_config(), changed)
        self.assertNotIn('key-one', repr(self.store.ai_profiles()))

    def test_delete_current_requires_explicit_selection_of_remaining_model(self):
        first = self.store.save_ai_profile(self.a)
        second = self.store.save_ai_profile(self.b)
        self.store.delete_ai_profile(first)
        self.assertIsNone(self.store.ai_config())
        self.assertEqual(len(self.store.ai_profiles()), 1)
        self.store.activate_ai_profile(second)
        self.assertEqual(self.store.ai_config(), self.b)
        self.store.delete_ai_profile(second)
        self.assertEqual(self.store.ai_profiles(), [])
        self.assertIsNone(self.store.ai_config())

    def test_failed_profile_write_preserves_all_saved_data(self):
        first = self.store.save_ai_profile(self.a)
        before = self.store.path.read_bytes()
        with patch('settings.os.replace', side_effect=OSError('disk full')):
            with self.assertRaises(SettingsError):
                self.store.save_ai_profile(self.b, first)
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertEqual(self.store.ai_config(), self.a)

    def test_malformed_profile_or_unknown_id_cannot_overwrite_saved_credentials(self):
        self.store.set('ai_profiles', {'items': 'broken', 'active_id': 'bad'})
        before = self.store.path.read_bytes()
        with self.assertRaises(SettingsError):
            self.store.save_ai_profile(self.a)
        self.assertEqual(self.store.path.read_bytes(), before)
        self.store.set('ai_profiles', None)
        self.store.save_ai_profile(self.a)
        before = self.store.path.read_bytes()
        for operation in (lambda: self.store.activate_ai_profile('missing'),
                          lambda: self.store.save_ai_profile(self.b, 'missing'),
                          lambda: self.store.delete_ai_profile('missing')):
            with self.assertRaises(SettingsError):
                operation()
        self.assertEqual(self.store.path.read_bytes(), before)
