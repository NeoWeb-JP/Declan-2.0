"""Security regression coverage for extracted HA ingress HTTP boundary."""

import unittest
from unittest.mock import patch

import http_ingress_security


class HandlerStub:
    def __init__(self, token=None, nonce=None):
        self.headers = {} if token is None else {"X-Declan-Ingress-Token": token}
        self._page_nonce = nonce
        self.sent = []

    def has_ingress_access(self):
        return http_ingress_security.has_ingress_access(self)

    def send_header(self, name, value):
        self.sent.append((name, value))


class IngressSecurityTests(unittest.TestCase):
    def test_valid_dedicated_token(self):
        with patch.dict("os.environ", {
            "DECLAN_INGRESS_TOKEN": "a" * 32,
            "DECLAN_ASSIST_TOKEN": "b" * 32,
        }):
            self.assertTrue(http_ingress_security.has_ingress_access(HandlerStub("a" * 32)))
            self.assertFalse(http_ingress_security.has_ingress_access(HandlerStub("b" * 32)))
            self.assertFalse(http_ingress_security.has_ingress_access(HandlerStub()))

    def test_reject_short_shared_or_missing_ingress_tokens(self):
        for ingress, assist in (("", "b" * 32), ("short", "b" * 32), ("a" * 32, "a" * 32)):
            with self.subTest(ingress=ingress):
                with patch.dict("os.environ", {
                    "DECLAN_INGRESS_TOKEN": ingress,
                    "DECLAN_ASSIST_TOKEN": assist,
                }):
                    self.assertFalse(http_ingress_security.has_ingress_access(HandlerStub(ingress)))

    def test_headers_match_existing_security_provider(self):
        with patch.dict("os.environ", {
            "DECLAN_INGRESS_TOKEN": "a" * 32,
            "DECLAN_ASSIST_TOKEN": "b" * 32,
        }):
            handler = HandlerStub("a" * 32, nonce="abc123")
            with patch.object(http_ingress_security, "response_headers", return_value={
                "Content-Security-Policy": "nonce-abc123", "X-Test-Ingress": "yes",
            }) as provider:
                http_ingress_security.send_security_headers(handler)
            provider.assert_called_once_with(ingress=True, nonce="abc123")
            self.assertEqual(handler.sent, [
                ("Content-Security-Policy", "nonce-abc123"), ("X-Test-Ingress", "yes"),
            ])

    def test_no_headers_attribute_fails_closed(self):
        handler = HandlerStub()
        del handler.headers
        with patch.object(http_ingress_security, "response_headers", return_value={}) as provider:
            http_ingress_security.send_security_headers(handler)
        provider.assert_called_once_with(ingress=False, nonce=None)


if __name__ == "__main__":
    unittest.main()
