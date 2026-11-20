"""Final retirement contract: legacy web root is gone, backend and native HA remain."""
from email.message import Message
import unittest
from pathlib import Path
from unittest.mock import patch
from server import Handler

class RetirementTests(unittest.TestCase):
    def test_root_denied_without_serving_legacy_html(self):
        handler = Handler.__new__(Handler)
        handler.path = "/"
        handler.client_address = ("127.0.0.1", 12345)
        handler.headers = Message()
        handler.headers["Host"] = "127.0.0.1:52737"
        handler.server = type("Server", (), {"server_port": 52737})()
        setattr(handler, 'send_json', lambda status, payload: setattr(handler, "result", (status, payload)))
        with patch.object(Handler, "has_ingress_access", return_value=False):
            handler.do_GET()
        result = getattr(handler, "result")
        self.assertEqual(result[0], 404)
        self.assertIn("native Declan Home Assistant", result[1]["error"])

    def test_native_panel_ships_with_the_integration(self):
        self.assertTrue(Path(__file__).resolve().parents[1].joinpath(
            "custom_components/declan_two/frontend/panel.js").exists())

if __name__ == "__main__":
    unittest.main()
