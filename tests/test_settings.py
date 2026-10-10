"""Persistence and session recovery checks, isolated from real user settings."""
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from rich.console import Console

import theme
from ai.client import AIConfig
from app import Application
from settings import SettingsStore, SettingsError
from ui import TerminalUI
from base.auth import AuthenticationExpired, PlatformUnavailable, authenticated_get
from AIMoocMain.api import AIMoocApi
from ZYKMoocMain.api import ZYKMoocApi


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SettingsStore(Path(self.temp.name) / "local")
        self.output = io.StringIO()
        self.ui = TerminalUI(console=Console(file=self.output, theme=theme.THEME, width=120))
        self.app = Application(self.ui, self.store)
        self.config = AIConfig("https://example.org/v1", "model", "secret-key")

    def test_restart_keeps_config_and_separate_platform_sessions(self):
        self.store.save_ai(self.config)
        self.store.save_session("mooc", Mock(access_token="mooc-secret"))
        self.store.save_session("zyk", Mock(access_token="zyk-secret"))
        self.store.set("confidence", 0.9)
        restarted = SettingsStore(self.store.directory)
        self.assertEqual(restarted.ai_config(), self.config)
        self.assertEqual(restarted.session("zyk")["access_token"], "zyk-secret")
        restarted.clear_session("mooc")
        self.assertIsNone(restarted.session("mooc"))
        self.assertEqual(restarted.get("confidence"), 0.9)
        self.assertIsNotNone(restarted.session("zyk"))
        self.assertNotIn("secret-key", repr(restarted.ai_config()))
        if os.name != "nt":
            self.assertEqual(self.store.path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(self.store.directory.stat().st_mode & 0o777, 0o700)

    def test_failed_atomic_write_preserves_old_config(self):
        self.store.save_ai(self.config)
        before = self.store.path.read_bytes()
        with patch("settings.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(SettingsError):
                self.store.set("ai", None)
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertEqual(list(self.store.directory.glob(".settings-*")), [])

    def test_corrupt_file_is_not_overwritten_or_echoed(self):
        self.store.directory.mkdir()
        self.store.path.write_text("secret-key BROKEN", encoding="utf-8")
        with self.assertRaises(SettingsError) as error:
            self.store.set("confidence", 0.8)
        self.assertNotIn("secret-key", str(error.exception))
        self.assertEqual(self.store.path.read_text(), "secret-key BROKEN")

    def test_first_ai_configuration_saved_then_reused_without_prompt(self):
        with patch.object(self.ui, "ai_config", return_value=self.config) as prompt:
            self.assertEqual(self.app.ai_configuration(), self.config)
            restarted = Application(self.ui, SettingsStore(self.store.directory))
            self.assertEqual(restarted.ai_configuration(), self.config)
            prompt.assert_called_once()
        self.assertNotIn("secret-key", self.output.getvalue())

    def test_storage_failure_does_not_stop_current_ai_config(self):
        with patch.object(self.ui, "ai_config", return_value=self.config), \
             patch.object(self.store, "save_ai", side_effect=SettingsError("无法保存")):
            self.assertEqual(self.app.ai_configuration(), self.config)
        self.assertIn("未持久化", self.output.getvalue())

    def client(self):
        client = Mock(access_token="new-secret")
        client.my_course_list.return_value = {"rows": [{"id": "c", "courseName": "课程"}]}
        return client

    def test_valid_login_restored_without_browser(self):
        self.store.save_session("mooc", Mock(access_token="cached-secret"))
        client = self.client()
        api = Mock(return_value=client)
        with patch.object(self.app, "login") as login, patch.object(self.ui, "courses", side_effect=lambda rows: rows):
            actual, rows = self.app.client_and_courses(api)
        login.assert_not_called()
        api.assert_called_once_with(access_token="cached-secret")
        client.my_course_list.assert_called_once_with(page_size=9999, strict=True)
        self.assertIs(actual, client)
        self.assertEqual(rows[0]["id"], "c")

    def test_expired_login_reauthenticates_once_and_replaces_cache(self):
        for failure_at in ("account", "courses"):
            with self.subTest(failure_at=failure_at):
                self.store.save_session("mooc", Mock(access_token="expired"))
                old, new = self.client(), self.client()
                old.my_course_list.side_effect = AuthenticationExpired()
                api = Mock(side_effect=[AuthenticationExpired() if failure_at == "account" else old, new])
                with patch.object(self.app, "login", return_value=("", "", "sso")) as login, \
                     patch.object(self.ui, "courses", return_value=[]):
                    self.app.client_and_courses(api)
                login.assert_called_once()
                self.assertEqual(api.call_count, 2)
                self.assertEqual(self.store.session("mooc")["access_token"], "new-secret")

    def test_network_failure_keeps_login_and_does_not_open_browser(self):
        self.store.save_session("mooc", Mock(access_token="cached"))
        api = Mock(side_effect=PlatformUnavailable("网络中断"))
        with patch.object(self.app, "login") as login:
            with self.assertRaises(PlatformUnavailable):
                self.app.client_and_courses(api)
        login.assert_not_called()
        self.assertEqual(self.store.session("mooc")["access_token"], "cached")

    def test_failed_course_response_never_saved_as_valid_login(self):
        client = self.client()
        client.my_course_list.return_value = {"code": 500}
        with patch.object(self.app, "login", return_value=("", "", "sso")):
            with self.assertRaises(PlatformUnavailable):
                self.app.client_and_courses(Mock(return_value=client))
        self.assertIsNone(self.store.session("mooc"))

    def test_settings_can_forget_credentials_independently(self):
        self.store.save_ai(self.config)
        self.store.save_session("mooc", Mock(access_token="m"))
        self.store.save_session("zyk", Mock(access_token="z"))
        with patch.object(self.ui, "settings_menu", side_effect=[2, 3, 0]):
            self.app.manage_settings()
        self.assertIsNone(self.store.ai_config())
        self.assertIsNone(self.store.session("mooc"))
        self.assertIsNotNone(self.store.session("zyk"))

    def test_edit_config_keeps_key_only_for_same_service(self):
        self.ui.input_fn = Mock(side_effect=["1", "", "new-model"])
        self.ui.secret_fn = Mock(return_value="")
        updated = self.ui.ai_config(self.config)
        self.assertEqual((updated.model, updated.api_key), ("new-model", "secret-key"))
        self.ui.input_fn = Mock(side_effect=["1", "https://other.example/v1", "other-model",
                                            "https://other.example/v1", "other-model"])
        self.ui.secret_fn = Mock(side_effect=["", "other-key"])
        updated = self.ui.ai_config(self.config)
        self.assertEqual(updated.api_key, "other-key")
        self.assertEqual(self.ui.secret_fn.call_count, 2)
        self.assertNotIn("secret-key", self.output.getvalue())
        self.assertNotIn("other-key", self.output.getvalue())


class AuthenticationTests(unittest.TestCase):
    def test_both_platforms_restore_identity_without_sso_exchange(self):
        for cls, module, payload, attribute in (
            (AIMoocApi, "AIMoocMain.api", {"code": 200, "data": {"id": "user", "displayName": "用户"}}, "user_id"),
            (ZYKMoocApi, "ZYKMoocMain.api", {"code": 200, "user": {"userId": "user", "nickName": "用户"}}, "student_id"),
        ):
            with self.subTest(platform=module):
                session = Mock(headers={})
                session.get.return_value.status_code = 200
                session.get.return_value.json.return_value = payload
                with patch("base.api_client.create_session", return_value=session), patch.object(cls, "_get_access_token") as exchange:
                    client = cls(access_token="cached")
                exchange.assert_not_called()
                self.assertEqual(getattr(client, attribute), "user")
                self.assertEqual(session.headers["Authorization"], "Bearer cached")
                self.assertFalse(session.get.call_args.kwargs["allow_redirects"])
                session.post.assert_not_called()

    def test_auth_expiry_distinguished_from_server_or_transport_failure(self):
        client = Mock(default_base_url="https://platform.example")
        for status, data, error in (
            (401, {}, AuthenticationExpired), (200, {"code": 401}, AuthenticationExpired),
            (200, {"code": "401"}, AuthenticationExpired), (403, {}, PlatformUnavailable),
            (503, {}, PlatformUnavailable), (200, {"code": 500}, PlatformUnavailable),
            (302, {}, PlatformUnavailable), (200, [], PlatformUnavailable),
        ):
            with self.subTest(status=status, data=data):
                client.session.get.return_value.status_code = status
                client.session.get.return_value.json.return_value = data
                with self.assertRaises(error):
                    authenticated_get(client, "/info")
        client.session.get.side_effect = requests.Timeout("secret-token")
        with self.assertRaises(PlatformUnavailable) as error:
            authenticated_get(client, "/info")
        self.assertNotIn("secret-token", str(error.exception))


if __name__ == "__main__":
    unittest.main()
