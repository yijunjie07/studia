"""Exercise the real local callback with synthetic credentials only."""
import threading
import unittest
from http.server import HTTPServer
from unittest.mock import patch

import requests

from NewMoocMain.oauth_login import OAuthLoginHandler


class CallbackPageTests(unittest.TestCase):
    def setUp(self):
        self.handler = OAuthLoginHandler()
        self.server = HTTPServer(("127.0.0.1", 0), self.handler.create_request_handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.session = requests.Session()
        self.session.trust_env = False
        self.addCleanup(self.session.close)
        self.url = "http://127.0.0.1:%s" % self.server.server_port

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_success_delivers_token_to_app_without_embedding_in_page(self):
        token = "synthetic-secret-</script><script>alert(1)</script>"
        with patch("NewMoocMain.oauth_login.threading.Timer") as timer:
            response = self.session.get(self.url + "/login", params={"token": token}, timeout=5)
            # Wait until the request handler has completed the handoff.
            self.session.get(self.url + "/", timeout=5)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.handler.token, token)
        self.assertIn("登录成功", response.text)
        self.assertNotIn(token, response.text)
        self.assertNotIn("synthetic-secret", response.text)
        self.assertNotIn("copyToken", response.text)
        self.assertIn("history.replaceState", response.text)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
        timer.assert_called_once_with(2.0, self.handler.stop_server)
        timer.return_value.start.assert_called_once()

    def test_missing_or_blank_token_does_not_complete_login(self):
        for query in ("", "?token=", "?token=%20%20"):
            with self.subTest(query=query):
                response = self.session.get(self.url + "/login" + query, timeout=5)
                self.assertEqual(response.status_code, 400)
                self.assertIn("登录未完成", response.text)
                self.assertIsNone(self.handler.token)

    def test_waiting_and_missing_pages_share_design_without_reflecting_url(self):
        response = self.session.get(self.url + "/", timeout=5)
        self.assertEqual(response.status_code, 200)
        self.assertIn("等待登录", response.text)
        response = self.session.get(self.url + "/synthetic-private-path", timeout=5)
        self.assertEqual(response.status_code, 404)
        self.assertIn("页面不存在", response.text)
        self.assertNotIn("synthetic-private-path", response.text)
        self.assertIsNone(self.handler.token)


if __name__ == "__main__":
    unittest.main()
