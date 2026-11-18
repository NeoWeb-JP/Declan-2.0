"""Final retirement contract: legacy web root is gone, backend and native HA remain."""
import unittest
from pathlib import Path
from unittest.mock import patch
from server import Handler

class RetirementTests(unittest.TestCase):
    def test_root_denied_without_serving_legacy_html(self):
        handler = Handler.__new__(Handler)
        handler.path = "/"
        handler.client_address = ("127.0.0.1", 12345)
        handler.headers = {"Host": "127.0.0.1:52737"}
        handler.server = type("Server", (), {"server_port": 52737})()
        handler.send_json = lambda status, payload: setattr(handler, "result", (status, payload))
        with patch.object(Handler, "has_ingress_access", return_value=False):
            handler.do_GET()
        self.assertEqual(handler.result[0], 404)
        self.assertIn("native Declan Home Assistant", handler.result[1]["error"])

    def test_backend_endpoints_and_native_panel_preserved(self):
        source = Path(__file__).resolve().parents[1].joinpath("server.py").read_text()
        self.assertIn('elif self.path == "/health":', source)
        # Request-origin routing now lives in the extracted request_origin module.
        origin_source = Path(__file__).resolve().parents[1].joinpath(
            "request_origin.py").read_text()
        self.assertIn('path == "/api/assist"', origin_source)
        self.assertIn("ingress_turn_orchestration.resolve_origin(", source)
        self.assertIn("resolve=request_origin.request_context", source)
        ingress = Path(__file__).resolve().parents[1].joinpath("ingress_turn_orchestration.py").read_text()
        self.assertIn("return resolve(path, body)", ingress)
        self.assertNotIn("webbrowser.open(", source)
        self.assertTrue(Path(__file__).resolve().parents[1].joinpath(
            "custom_components/declan_two/frontend/panel.js").exists())

if __name__ == "__main__":
    unittest.main()
