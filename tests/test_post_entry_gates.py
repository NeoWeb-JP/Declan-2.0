"""Regression coverage for authentication, STT and content-type gate ordering."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import post_entry_gates


class PostEntryGatesTests(unittest.TestCase):
    def setUp(self):
        self.auth = MagicMock(name="auth")
        self.route = MagicMock(name="route")
        self.origin = MagicMock(name="origin")
        self.transcribe = MagicMock(name="transcribe")

    def run_gate(self, path, *, allowed=True, json_allowed=True):
        handler = SimpleNamespace(path=path)
        with patch.object(post_entry_gates.post_request_entry, "enforce_preflight", return_value=allowed) as auth, \
             patch.object(post_entry_gates.post_request_entry, "enforce_content_type", return_value=json_allowed) as content:
            result = post_entry_gates.enforce(
                handler, assist_token="secret", ingress=False,
                authenticate_assist=self.auth, enforce_known_route=self.route,
                enforce_origin=self.origin, transcribe=self.transcribe,
            )
        return result, auth, content, handler

    def test_denied_request_never_reaches_speech_or_content_type(self):
        result, auth, content, handler = self.run_gate("/api/stt", allowed=False)
        self.assertFalse(result)
        auth.assert_called_once_with(
            handler, assist_token="secret", ingress=False,
            authenticate_assist=self.auth, enforce_known_route=self.route,
            enforce_origin=self.origin,
        )
        self.transcribe.assert_not_called()
        content.assert_not_called()

    def test_authenticated_stt_skips_json_gate(self):
        result, _, content, _ = self.run_gate("/api/stt")
        self.assertFalse(result)
        self.transcribe.assert_called_once_with()
        content.assert_not_called()

    def test_chat_requires_json_content_type(self):
        result, _, content, handler = self.run_gate("/api/chat", json_allowed=False)
        self.assertFalse(result)
        content.assert_called_once_with(handler)
        self.transcribe.assert_not_called()

    def test_authorized_json_request_continues(self):
        result, _, content, handler = self.run_gate("/api/settings/ai")
        self.assertTrue(result)
        content.assert_called_once_with(handler)
        self.transcribe.assert_not_called()

    def test_stt_callback_error_is_not_swallowed(self):
        self.transcribe.side_effect = ValueError("speech failed")
        with self.assertRaisesRegex(ValueError, "speech failed"):
            self.run_gate("/api/stt")


if __name__ == "__main__":
    unittest.main()
