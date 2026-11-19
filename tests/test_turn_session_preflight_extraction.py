"""Regression checks for session and preflight extraction."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import turn_session_preflight


class SessionPreflightExtractionTests(unittest.TestCase):
    def setUp(self):
        self.handler = Mock()
        self.r = Mock()
        self.r.monotonic.return_value = 123
        self.r.secrets.token_urlsafe.return_value = "new-session"
        self.r.turn_session_entry.prepare.return_value = SimpleNamespace(
            source="voice", scope="home", origin_device="kitchen",
            satellite="kitchen", recent_context=("lights", "device", "information"))
        self.r.turn_preflight_entry.resolve.return_value = SimpleNamespace(
            session_id="session", phrase="turn on light",
            effective_message="turn on light", pending_retry=None)

    def prepare(self):
        return turn_session_preflight.prepare(
            self.handler, {"message": "turn on light"}, "turn on light", "session", r=self.r)

    def test_session_rejection_stops_preflight(self):
        self.r.turn_session_entry.prepare.return_value = None
        self.assertIsNone(self.prepare())
        self.r.turn_preflight_entry.resolve.assert_not_called()

    def test_preflight_rejection_stops_dispatch(self):
        self.r.turn_preflight_entry.resolve.return_value = None
        self.assertIsNone(self.prepare())

    def test_success_preserves_context_and_retry(self):
        self.r.turn_preflight_entry.resolve.return_value.pending_retry = "retry"
        result = self.prepare()
        self.assertEqual((result.source, result.scope, result.origin_device, result.satellite),
                         ("voice", "home", "kitchen", "kitchen"))
        self.assertEqual((result.last_lights, result.last_device, result.last_information),
                         ("lights", "device", "information"))
        self.assertEqual((result.session_id, result.phrase, result.pending_retry),
                         ("session", "turn on light", "retry"))

    def test_live_server_dependencies_are_used(self):
        self.prepare()
        self.r.turn_session_entry.prepare.assert_called_once()
        self.r.turn_preflight_entry.resolve.assert_called_once()
        self.assertIs(self.r.turn_session_entry.prepare.call_args.args[0], self.handler)
        self.assertIs(self.r.turn_preflight_entry.resolve.call_args.args[0], self.handler)


if __name__ == "__main__":
    unittest.main()
