"""One phone: save the code, scan it in the 知到 App while the page is frozen, come back signed in."""
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from core.settings import SettingsStore
from web.server import PLATFORMS, Studia


class ServerWatchesQrTest(unittest.TestCase):
    def test_confirmation_is_taken_without_the_page_and_reported_when_it_returns(self):
        client = Mock(access_token="cookies")
        client.login_qr.return_value = ("qr-token", b"\x89PNG")
        client.login_qr_status.side_effect = [{"status": -1}, {"status": 2}, {"status": 1, "oncePassword": "once"}]
        app = Studia(SettingsStore(tempfile.mkdtemp()), oauth=Mock(return_value=None))
        with patch.dict(PLATFORMS["zhs"], {"api": lambda: client}), patch("web.server.time.sleep"):
            qid = app.login_start("zhs")["id"]
            for _ in range(200):
                if client.shared_exam_sso.called:  # the last step of a finished scan
                    break
                threading.Event().wait(0.01)  # time.sleep itself is patched out for the watcher
        client.finish_qr_login.assert_called_once_with("once")
        client.login_qr.assert_called_once()  # an expiry seen while nobody looks is left to the page
        self.assertEqual(app.login_status("zhs", qid)["status"], "done")


if __name__ == "__main__":
    unittest.main()
