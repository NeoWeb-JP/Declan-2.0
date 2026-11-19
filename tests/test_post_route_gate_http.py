"""POST route allowlist and unknown-route rejection regression tests."""

import unittest
from unittest.mock import Mock

from declan.http.post_route_gate_http import POST_ROUTES, enforce_known_route


class PostRouteGateTests(unittest.TestCase):
    def test_known_routes(self):
        for path in POST_ROUTES:
            with self.subTest(path=path):
                handler = Mock(path=path)
                self.assertTrue(enforce_known_route(handler))
                handler.send_json.assert_not_called()

    def test_unknown_route_returns_404(self):
        for path in ("/api/missing", "/api/updates/status", "/api/chat/", ""):
            with self.subTest(path=path):
                handler = Mock(path=path)
                self.assertFalse(enforce_known_route(handler))
                handler.send_json.assert_called_once_with(404, {"error": "Not found."})

    def test_assist_and_native_routes_remain_known(self):
        for path in (
            "/api/assist", "/api/assist/history", "/api/native/intents",
            "/api/native/routines", "/api/native/routine-responses",
        ):
            self.assertIn(path, POST_ROUTES)


if __name__ == "__main__":
    unittest.main()
