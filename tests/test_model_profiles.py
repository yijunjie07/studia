import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai.client import AIConfig
from settings import SettingsStore, SettingsError


class ModelProfilesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SettingsStore(Path(self.temp.name))
        self.a = AIConfig('https://one.example/v1', 'same-model', 'key-one')
        self.b = AIConfig('https://two.example/v1', 'same-model', 'key-two')

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
