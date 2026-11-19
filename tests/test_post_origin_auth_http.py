"""POST scoped bearer and local-origin authorization regressions."""

import unittest
from unittest.mock import Mock

from declan.http.post_origin_auth_http import BEARER_ALLOWED_PATHS, enforce_access, is_authorized


class PostOriginAuthTests(unittest.TestCase):
    def allowed(self, path="/api/chat", *, token="x" * 32, supplied=None,
                ingress=False, ip="192.0.2.1", origin=None):
        return is_authorized(
            path=path, token=token,
            supplied=supplied if supplied is not None else "Bearer " + token,
            ingress=ingress, client_ip=ip, origin=origin, port=8123,
        )

    def test_scoped_bearer_routes(self):
        for path in BEARER_ALLOWED_PATHS:
            with self.subTest(path=path):
                self.assertTrue(self.allowed(path))

    def test_short_or_invalid_token_rejected(self):
        self.assertFalse(self.allowed(token="short"))
        self.assertFalse(self.allowed(supplied="Bearer wrong"))
        self.assertFalse(self.allowed(token=""))

    def test_bearer_does_not_authorize_unlisted_route(self):
        self.assertFalse(self.allowed("/api/settings/import"))

    def test_ingress_and_local_origin(self):
        self.assertTrue(self.allowed("/api/settings/import", ingress=True, token=""))
        for origin in ("http://127.0.0.1:8123", "http://localhost:8123"):
            self.assertTrue(self.allowed("/api/settings/import", token="", ip="127.0.0.1", origin=origin))
        self.assertFalse(self.allowed("/api/settings/import", token="", ip="127.0.0.1", origin="https://evil.example"))
        self.assertFalse(self.allowed("/api/settings/import", token="", ip="192.0.2.1", origin="http://localhost:8123"))

    def test_denial_and_allowance_http_contract(self):
        handler = Mock(path="/api/settings/import", client_address=("192.0.2.1", 9000))
        handler.server.server_port = 8123
        handler.headers.get.return_value = None
        self.assertFalse(enforce_access(handler, token="", ingress=False))
        handler.send_json.assert_called_once_with(
            403, {"error": "Send requests from the local Declan page."},
        )
        handler.send_json.reset_mock()
        self.assertTrue(enforce_access(handler, token="", ingress=True))
        handler.send_json.assert_not_called()


if __name__ == "__main__":
    unittest.main()
