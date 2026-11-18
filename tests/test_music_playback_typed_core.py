"""Typed playback provider results and compatibility with existing callers."""
import unittest
from unittest.mock import Mock, patch

import music
from execution_results import ExecutionResult, Outcome


class PlaybackCoreTypedTests(unittest.TestCase):
    def test_missing_connection_returns_typed_not_configured(self):
        result = music._play_provider(("kitchen", "country", "spotify"), None, Mock())
        self.assertIsInstance(result, ExecutionResult)
        self.assertIs(result.outcome, Outcome.NOT_CONFIGURED)
        self.assertEqual(music.play(("kitchen", "country", "spotify"), None, Mock()),
                         result.as_legacy_pair())

    def test_busy_lock_returns_typed_busy(self):
        with patch.object(music.RUNTIME, "handoff") as lock:
            lock.acquire.return_value = False
            result = music._play_provider(("kitchen", "country", "spotify"), "ha", Mock())
        self.assertIs(result.outcome, Outcome.BUSY)
        lock.release.assert_not_called()

    def test_inventory_error_preserves_outcome_and_unlocks(self):
        with patch.object(music.RUNTIME, "handoff") as lock:
            lock.acquire.return_value = True
            result = music._play_provider(("kitchen", "country", "spotify"), "ha",
                                          lambda _: ([], "unavailable"))
        self.assertIs(result.outcome, Outcome.UNAVAILABLE)
        lock.release.assert_called_once()

    def test_missing_origin_room_is_unresolved(self):
        with patch.object(music.RUNTIME, "handoff") as lock:
            lock.acquire.return_value = True
            result = music._play_provider((None, "country", "spotify"), "ha",
                                          lambda _: ([], None), origin="unknown")
        self.assertIs(result.outcome, Outcome.UNRESOLVED)

    def test_unapproved_room_does_not_start_playback(self):
        with patch.object(music.RUNTIME, "handoff") as lock, \
             patch.object(music, "music_players", return_value=({}, {})), \
             patch.object(music, "request") as request:
            lock.acquire.return_value = True
            result = music._play_provider(("kitchen", "country", "spotify"), "ha",
                                          lambda _: ([], None))
        self.assertIs(result.outcome, Outcome.UNRESOLVED)
        request.assert_not_called()

    def test_public_play_api_accepts_typed_core(self):
        with patch.object(music, "_play_provider",
                          return_value=ExecutionResult("Playing", Outcome.CONFIRMED)):
            self.assertEqual(music.play(("kitchen", "country", "spotify"), "ha", Mock()),
                             ("Playing", "confirmed"))

    def test_typed_entrypoint_accepts_typed_core(self):
        with patch.object(music, "_play_provider",
                          return_value=ExecutionResult("Playing", Outcome.CONFIRMED)):
            result = music.play_result(("kitchen", "country", "spotify"), "ha", Mock())
        self.assertIs(result.outcome, Outcome.CONFIRMED)


if __name__ == "__main__":
    unittest.main()
