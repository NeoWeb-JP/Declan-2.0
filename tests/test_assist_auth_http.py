"""Assist POST authentication regression tests."""

import unittest
from unittest.mock import Mock

from declan.voice.assist_auth_http import authenticate_assist


class AssistAuthHttpTests(unittest.TestCase):
    def setUp(self):
        self.handler = Mock()
        self.handler.client_address = ("192.0.2.10", 9000)
        self.handler.headers.get.return_value = "Bearer secret"
        self.handler.server.bad_tokens.check.return_value = 0

    def test_valid_token_allows_request(self):
        self.assertFalse(authenticate_assist(self.handler, token="secret"))
        self.handler.server.bad_tokens.check.assert_called_once_with("192.0.2.10", True)
        self.handler.send_json.assert_not_called()

    def test_invalid_token_is_rejected_and_connection_closed(self):
        self.handler.headers.get.return_value = "Bearer incorrect"
        self.assertTrue(authenticate_assist(self.handler, token="secret"))
        self.assertTrue(self.handler.close_connection)
        self.handler.server.bad_tokens.check.assert_called_once_with("192.0.2.10", False)
        self.handler.send_json.assert_called_once_with(
            401, {"error": "Invalid bridge credentials."},
        )

    def test_missing_token_is_rejected(self):
        self.assertTrue(authenticate_assist(self.handler, token=""))
        self.handler.send_json.assert_called_once_with(
            401, {"error": "Invalid bridge credentials."},
        )

    def test_throttle_uses_empty_429_response(self):
        self.handler.server.bad_tokens.check.return_value = 30
        self.assertTrue(authenticate_assist(self.handler, token="secret"))
        self.assertTrue(self.handler.close_connection)
        self.handler.send_response.assert_called_once_with(429)
        self.handler.send_header.assert_any_call("Retry-After", "30")
        self.handler.send_header.assert_any_call("Content-Length", "0")
        self.handler.send_header.assert_any_call("Cache-Control", "no-store")
        self.handler.end_headers.assert_called_once()
        self.handler.send_json.assert_not_called()


if __name__ == "__main__":
    unittest.main()
