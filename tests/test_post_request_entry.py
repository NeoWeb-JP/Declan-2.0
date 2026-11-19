"""POST entry boundary preserves diagnostics and authentication ordering."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from declan.http import post_request_entry


class PostEntryTests(unittest.TestCase):
    def test_diagnostics_only_for_conversation_and_speech_routes(self):
        for path in ("/api/chat", "/api/assist", "/api/stt", "/api/tts", "/api/assist/history"):
            with self.subTest(path=path):
                handler = SimpleNamespace(path=path)
                callback = MagicMock(return_value="done")
                with patch.object(post_request_entry.diagnostics, "request") as request:
                    self.assertEqual(post_request_entry.dispatch(handler, handle_post=callback), "done")
                request.assert_called_once_with(path)
                callback.assert_called_once_with()

    def test_management_route_does_not_create_diagnostic_context(self):
        handler = SimpleNamespace(path="/api/settings/ai")
        callback = MagicMock(return_value="done")
        with patch.object(post_request_entry.diagnostics, "request") as request:
            self.assertEqual(post_request_entry.dispatch(handler, handle_post=callback), "done")
        request.assert_not_called()
        callback.assert_called_once_with()

    def test_preflight_delegates_all_authentication_gates(self):
        handler = SimpleNamespace(path="/api/chat")
        callbacks = [MagicMock() for _ in range(3)]
        with patch.object(post_request_entry.post_request_preflight, "enforce", return_value=False) as gate:
            self.assertFalse(post_request_entry.enforce_preflight(
                handler, assist_token="secret", ingress=False,
                authenticate_assist=callbacks[0],
                enforce_known_route=callbacks[1], enforce_origin=callbacks[2],
            ))
        gate.assert_called_once_with(
            handler, assist_token="secret", ingress=False,
            authenticate_assist=callbacks[0],
            enforce_known_route=callbacks[1], enforce_origin=callbacks[2],
        )

    def test_content_type_gate_result_is_preserved(self):
        handler = SimpleNamespace(path="/api/chat")
        with patch.object(post_request_entry.post_content_type_http, "enforce_json_content_type", return_value=False) as gate:
            self.assertFalse(post_request_entry.enforce_content_type(handler))
        gate.assert_called_once_with(handler)


if __name__ == "__main__":
    unittest.main()
