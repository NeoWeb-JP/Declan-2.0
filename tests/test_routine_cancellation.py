"""Mapped routine cancellation results and request contract."""

import json
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from execution_results import Outcome
from declan.turn import routine_cancellation


class Response:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, size):
        assert size == 4096
        return b"ok"


class RoutineCancellationTests(unittest.TestCase):
    def test_no_connection_reports_not_configured(self):
        registry = SimpleNamespace(snapshot=MagicMock())
        result, context = routine_cancellation.stop_pending_routines_result(
            connection_factory=lambda: None, active_registry=registry,
        )
        self.assertEqual(result.outcome, Outcome.NOT_CONFIGURED)
        self.assertIsNone(context)
        registry.snapshot.assert_not_called()

    def test_no_active_routines_returns_confirmed_without_http(self):
        opener = SimpleNamespace(open=MagicMock())
        result, _ = routine_cancellation.stop_pending_routines_result(
            connection_factory=lambda: ("http://ha", {}, opener),
            active_registry=SimpleNamespace(snapshot=lambda: {}),
        )
        self.assertEqual(result.outcome, Outcome.CONFIRMED)
        opener.open.assert_not_called()

    def test_active_routine_sends_script_turn_off_without_claiming_rollback(self):
        opener = SimpleNamespace(open=MagicMock(return_value=Response()))
        result, context = routine_cancellation.stop_pending_routines_result(
            connection_factory=lambda: ("http://ha", {"Authorization": "Bearer test"}, opener),
            active_registry=SimpleNamespace(snapshot=lambda: {"Movie Time": "script.movie_time"}),
        )
        self.assertEqual(result.outcome, Outcome.UNVERIFIED)
        self.assertIsNone(context)
        self.assertIn("Cancellation requested for: Movie Time.", result.reply)
        self.assertIn("Already completed actions were not rolled back.", result.reply)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "http://ha/api/services/script/turn_off")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(json.loads(request.data), {"entity_id": "script.movie_time"})
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 4)

    def test_failed_request_reports_unconfirmed_routine(self):
        opener = SimpleNamespace(open=MagicMock(side_effect=OSError("offline")))
        result, _ = routine_cancellation.stop_pending_routines_result(
            connection_factory=lambda: ("http://ha", {}, opener),
            active_registry=SimpleNamespace(snapshot=lambda: {"Good Night": "script.good_night"}),
        )
        self.assertEqual(result.outcome, Outcome.UNVERIFIED)
        self.assertIn("Could not confirm cancellation request for: Good Night.", result.reply)


if __name__ == "__main__":
    unittest.main()
