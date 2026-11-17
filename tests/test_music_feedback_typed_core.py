"""Typed outcomes returned by the music feedback provider implementation."""
import unittest
from unittest.mock import Mock, patch

import music
from execution_results import ExecutionResult, Outcome


class FeedbackCoreTypedTests(unittest.TestCase):
    def test_missing_connection_is_typed_and_legacy_api_unchanged(self):
        core = music._feedback_provider(("i love this song", None), None, Mock())
        self.assertIsInstance(core, ExecutionResult)
        self.assertIs(core.outcome, Outcome.UNAVAILABLE)
        self.assertEqual(music.feedback(("i love this song", None), None, Mock()),
                         core.as_legacy_pair())

    def test_inventory_error_is_typed(self):
        with patch.object(music, "HANDOFF") as lock:
            lock.acquire.return_value = True
            result = music._feedback_provider(
                ("i love this song", None), "connection",
                lambda _: ([], "unavailable"),
            )
        self.assertIs(result.outcome, Outcome.UNAVAILABLE)
        lock.release.assert_called_once()

    def test_ambiguous_active_players_are_unresolved(self):
        with patch.object(music, "HANDOFF") as lock, \
             patch.object(music, "music_players", return_value=({}, {})), \
             patch.object(music, "playback_sources", return_value={}):
            lock.acquire.return_value = True
            result = music._feedback_provider(
                ("i love this song", None), "connection", lambda _: ([], None),
            )
        self.assertIs(result.outcome, Outcome.UNRESOLVED)
        self.assertIn("which active", result.reply)

    def test_legacy_feedback_adapter_accepts_typed_core(self):
        with patch.object(music, "_feedback_provider",
                          return_value=ExecutionResult("Saved", Outcome.MUSIC_FEEDBACK)):
            self.assertEqual(music.feedback(("i love this song", None), "connection", Mock()),
                             ("Saved", "music_feedback"))

    def test_feedback_result_entrypoint_accepts_typed_core(self):
        with patch.object(music, "_feedback_provider",
                          return_value=ExecutionResult("Saved", Outcome.MUSIC_FEEDBACK)):
            result = music.feedback_result(("i love this song", None), "connection", Mock())
        self.assertIs(result.outcome, Outcome.MUSIC_FEEDBACK)


if __name__ == "__main__":
    unittest.main()
