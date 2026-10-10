"""Detect only during connection checks; remember a successful protocol."""
import tempfile
import unittest
from contextlib import nullcontext
from unittest.mock import Mock

import requests

from ai.client import AIClient, AIConfig, AIError
from app import Application
from settings import SettingsStore
from tests.test_ai_protocols import ANSWER, response_payload


def reply(status=200, payload=None):
    response = Mock(status_code=status)
    response.json.return_value = payload if payload is not None else {
        'choices': [{'finish_reason': 'stop', 'message': {'content': ANSWER}}]}
    return response


class DetectionTests(unittest.TestCase):
    def test_full_urls_infer_protocol_without_probe(self):
        for suffix, protocol in [('/responses', 'responses'), ('/chat/completions', 'chat_completions')]:
            config = AIConfig('https://example.org/v1' + suffix, 'model', 'test-key')
            self.assertEqual(config.api_format, protocol)
            self.assertEqual(config.endpoint, config.base_url)

    def test_chat_success_is_remembered_without_responses_request(self):
        config = AIConfig('https://example.org/v1', 'model', 'test-key')
        session = Mock()
        session.post.return_value = reply()
        AIClient(config, session).check_connection()
        self.assertEqual(config.api_format, 'chat_completions')
        session.post.assert_called_once()

    def test_unsupported_chat_falls_back_once_and_remembers_responses(self):
        for status, payload in [(405, {}), (501, {}),
                                (404, {'error': {'code': 'endpoint_not_found'}}),
                                (400, {'error': {'code': 'unsupported_endpoint'}})]:
            with self.subTest(status=status):
                config = AIConfig('https://example.org/v1', 'model', 'test-key')
                session = Mock()
                session.post.side_effect = [reply(status, payload), reply(payload=response_payload()),
                                            reply(payload=response_payload())]
                client = AIClient(config, session)
                client.check_connection()
                self.assertEqual(config.api_format, 'responses')
                self.assertEqual(client.answer({'title': 'test'})['answer'], 'A')
                self.assertEqual([c.args[0] for c in session.post.call_args_list],
                                 ['https://example.org/v1/chat/completions',
                                  'https://example.org/v1/responses', 'https://example.org/v1/responses'])

    def test_auth_quota_network_model_and_bad_answers_do_not_trigger_fallback(self):
        failures = [reply(401, {}), reply(403, {}), reply(429, {}), reply(503, {}),
                    reply(404, {'error': {'code': 'model_not_found'}}), reply(404, {}),
                    reply(400, {'error': {'code': 'insufficient_quota'}}),
                    reply(400, {}), requests.Timeout('secret'),
                    reply(payload={'choices': []})]
        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                config = AIConfig('https://example.org/v1', 'model', 'test-key')
                session = Mock()
                session.post.side_effect = [failure]
                with self.assertRaises(AIError):
                    AIClient(config, session).check_connection()
                session.post.assert_called_once()
                self.assertEqual(config.api_format, 'auto')

    def test_failed_fallback_does_not_remember_unverified_protocol(self):
        config = AIConfig('https://example.org/v1', 'model', 'test-key')
        session = Mock()
        session.post.side_effect = [reply(405, {}), reply(401, {})]
        with self.assertRaises(AIError):
            AIClient(config, session).check_connection()
        self.assertEqual(config.api_format, 'auto')

    def test_application_persists_detection_and_health_without_changing_other_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SettingsStore(directory)
            config = AIConfig('https://example.org/v1', 'model', 'test-key', provider_name='Mine')
            store.save_ai_profile(config)
            other = AIConfig('https://other.example/v1', 'model', 'other-key')
            store.save_ai_profile(other)
            session = Mock()
            session.post.side_effect = [reply(405, {}), reply(payload=response_payload())]
            view = Mock()
            view.activity.return_value = nullcontext()
            Application(view, store).verify_ai(config, AIClient(config, session))
            restarted = SettingsStore(directory)
            self.assertEqual(restarted.ai_config().api_format, 'responses')
            self.assertEqual(restarted.ai_health(restarted.ai_config())['status'], 'ok')
            self.assertEqual(restarted.ai_profiles()[1].config, other)
