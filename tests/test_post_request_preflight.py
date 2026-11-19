"""POST preflight must preserve distinct Assist and management authentication."""
from typing import Any
import unittest
from types import SimpleNamespace
import post_request_preflight


class PostPreflightTests(unittest.TestCase):
    def check(self, path, *, assist=False, known=True, origin=True):
        calls: list[tuple[Any, ...]]
        calls = []
        handler = SimpleNamespace(path=path)
        def authenticate(h, *, token):
            calls.append(("assist", token))
            return assist
        def known_route(h):
            calls.append(("known",))
            return known
        def origin_access(h, *, token, ingress):
            calls.append(("origin", token, ingress))
            return origin
        allowed = post_request_preflight.enforce(
            handler, assist_token="token", ingress=False,
            authenticate_assist=authenticate, enforce_known_route=known_route,
            enforce_origin=origin_access,
        )
        return allowed, calls

    def test_assist_auth_is_exclusive(self):
        self.assertEqual(self.check("/api/assist", assist=True),
                         (False, [("assist", "token")]))
        self.assertEqual(self.check("/api/assist/history"),
                         (True, [("assist", "token")]))

    def test_management_requires_known_route_and_origin(self):
        self.assertEqual(self.check("/api/updates", known=False),
                         (False, [("known",)]))
        self.assertEqual(self.check("/api/updates", origin=False),
                         (False, [("known",), ("origin", "token", False)]))
        self.assertEqual(self.check("/api/updates"),
                         (True, [("known",), ("origin", "token", False)]))


if __name__ == "__main__":
    unittest.main()
