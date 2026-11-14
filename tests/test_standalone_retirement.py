"""The HA ingress panel remains available, but the standalone dashboard does not."""
import unittest
from unittest.mock import patch

from server import Handler


class StandaloneRetirementTests(unittest.TestCase):
    def handler(self, ingress):
        handler = Handler.__new__(Handler)
        handler.path = "/"
        handler.client_address = ("127.0.0.1", 12345)
        handler.headers = {"Host": "127.0.0.1:52737"}
        handler.server = type("Server", (), {"server_port": 52737})()
        handler.send_json = lambda status, payload: setattr(handler, "result", (status, payload))
        handler.send_body = lambda status, data, content_type: setattr(handler, "result", (status, content_type))
        return handler

    def test_local_dashboard_is_retired(self):
        handler = self.handler(False)
        with patch.object(Handler, "has_ingress_access", return_value=False):
            handler.do_GET()
        self.assertEqual(handler.result[0], 404)

    def test_authenticated_ingress_still_serves_panel(self):
        handler = self.handler(True)
        with patch.object(Handler, "has_ingress_access", return_value=True):
            handler.do_GET()
        self.assertEqual(handler.result, (200, "text/html; charset=utf-8"))


if __name__ == "__main__":
    unittest.main()
