"""Regression tests for the Home Assistant ingress token environment gate."""
from email.message import Message
import os
import unittest
from unittest.mock import patch

import server


class IngressTokenEnvironmentDefaultsTests(unittest.TestCase):
    def allowed(self, environment, supplied):
        handler = object.__new__(server.Handler)
        handler.headers = Message()
        handler.headers["X-Declan-Ingress-Token"] = supplied
        with patch.dict(os.environ, environment, clear=True):
            return handler.has_ingress_access()

    def test_unset_empty_and_short_tokens_fail_closed(self):
        for token in (None, "", "short", "a" * 31):
            settings = {} if token is None else {"DECLAN_INGRESS_TOKEN": token}
            with self.subTest(token=token):
                self.assertFalse(self.allowed(settings, token or ""))

    def test_valid_token_requires_exact_match(self):
        token = "i" * 32
        settings = {"DECLAN_INGRESS_TOKEN": token}
        self.assertTrue(self.allowed(settings, token))
        self.assertFalse(self.allowed(settings, ""))
        self.assertFalse(self.allowed(settings, "I" * 32))
        self.assertFalse(self.allowed(settings, token + " "))

    def test_ingress_token_must_differ_from_assist_token(self):
        token = "s" * 32
        self.assertFalse(self.allowed({
            "DECLAN_INGRESS_TOKEN": token,
            "DECLAN_ASSIST_TOKEN": token}, token))
        self.assertTrue(self.allowed({
            "DECLAN_INGRESS_TOKEN": token,
            "DECLAN_ASSIST_TOKEN": "a" * 32}, token))


if __name__ == "__main__":
    unittest.main()
