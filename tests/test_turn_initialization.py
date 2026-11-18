"""Turn initialization must not load context for duplicate captures."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import turn_initialization as turn


class TurnInitializationTests(unittest.TestCase):
    def setUp(self):
        self.handler = SimpleNamespace(path="/api/assist")
        self.body = {"speaker": "test"}
        self.kwargs = dict(
            message="hello", session_id="session", arbiter=object(),
            normalize=str.lower, new_session_id=lambda: "new",
            sessions={}, lock=object(), now=42.0, idle_seconds=300,
            retrieve=lambda *args: None,
        )

    def test_duplicate_suppresses_context_lookup(self):
        with patch.object(turn.request_origin, "request_context", return_value=("assist", "room", "device", "satellite")), patch.object(
            turn.assist_capture_http, "suppress_duplicate", return_value=True,
        ) as duplicate, patch.object(turn.session_context_access, "load_recent_context") as context:
            self.assertIsNone(turn.prepare(self.handler, self.body, **self.kwargs))
            duplicate.assert_called_once()
            context.assert_not_called()

    def test_non_duplicate_loads_scoped_context(self):
        recent = ("lights", "device", "information")
        with patch.object(turn.request_origin, "request_context", return_value=("assist", "room", "device", "satellite")), patch.object(
            turn.assist_capture_http, "suppress_duplicate", return_value=False,
        ), patch.object(turn.session_context_access, "load_recent_context", return_value=recent) as context:
            result = turn.prepare(self.handler, self.body, **self.kwargs)
            self.assertEqual(result.recent_context, recent)
            self.assertEqual(result.scope, "room")
            self.assertEqual(result.origin_device, "device")
            self.assertEqual(context.call_args.kwargs["session_id"], "session")
            self.assertEqual(context.call_args.kwargs["scope"], "room")


if __name__ == "__main__":
    unittest.main()
