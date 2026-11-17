"""Music control provider typed outcomes and public compatibility."""
import unittest
from unittest.mock import Mock, patch

import music
from execution_results import ExecutionResult, Outcome


class ControlCoreTypedTests(unittest.TestCase):
    def test_no_connection_returns_typed_not_configured(self):
        result = music._control_provider(("media_pause", "kitchen"), None, Mock())
        self.assertIsInstance(result, ExecutionResult)
        self.assertIs(result.outcome, Outcome.NOT_CONFIGURED)
        self.assertEqual(music.control(("media_pause", "kitchen"), None, Mock()),
                         result.as_legacy_pair())

    def test_busy_lock_returns_typed_busy(self):
        with patch.object(music, "HANDOFF") as lock:
            lock.acquire.return_value = False
            result = music._control_provider(("media_pause", "kitchen"), "ha", Mock())
        self.assertIs(result.outcome, Outcome.BUSY)
        lock.release.assert_not_called()

    def test_inventory_failure_preserves_unavailable(self):
        with patch.object(music, "HANDOFF") as lock:
            lock.acquire.return_value = True
            result = music._control_provider(("media_pause", "kitchen"), "ha",
                                             lambda _: ([], "unavailable"))
        self.assertIs(result.outcome, Outcome.UNAVAILABLE)
        lock.release.assert_called_once()

    def test_unqualified_stop_without_active_players_is_confirmed(self):
        with patch.object(music, "HANDOFF") as lock, \
             patch.object(music, "music_players", return_value=({}, {})):
            lock.acquire.return_value = True
            result = music._control_provider(("media_stop", None), "ha",
                                             lambda _: ([], None))
        self.assertIs(result.outcome, Outcome.CONFIRMED)
        self.assertIn("no active", result.reply.lower())

    def test_unapproved_room_is_unresolved_without_dispatch(self):
        with patch.object(music, "HANDOFF") as lock, \
             patch.object(music, "music_players", return_value=({}, {})), \
             patch.object(music, "request") as request:
            lock.acquire.return_value = True
            result = music._control_provider(("media_pause", "kitchen"), "ha",
                                             lambda _: ([], None))
        self.assertIs(result.outcome, Outcome.UNRESOLVED)
        request.assert_not_called()

    def test_public_control_api_accepts_typed_core(self):
        with patch.object(music, "_control_provider",
                          return_value=ExecutionResult("Paused", Outcome.CONFIRMED)):
            self.assertEqual(music.control(("media_pause", "kitchen"), "ha", Mock()),
                             ("Paused", "confirmed"))

    def test_typed_entrypoint_accepts_typed_core(self):
        with patch.object(music, "_control_provider",
                          return_value=ExecutionResult("Paused", Outcome.CONFIRMED)):
            result = music.control_result(("media_pause", "kitchen"), "ha", Mock())
        self.assertIs(result.outcome, Outcome.CONFIRMED)


if __name__ == "__main__":
    unittest.main()
