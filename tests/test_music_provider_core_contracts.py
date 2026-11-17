"""Validate music provider results before they leave legacy public APIs."""
import unittest
from unittest.mock import patch, Mock

import music
from execution_results import ExecutionResult, Outcome
from music_provider_result import PlayerAvailability


class MusicProviderCoreContractTests(unittest.TestCase):
    def test_player_availability_is_typed_frozen_and_preserves_boolean_api(self):
        for state in (None, "unknown", "unavailable", "playing", "paused", "idle", "off", "future_state", ""):
            with self.subTest(state=state):
                expected = state not in (None, "unknown", "unavailable")
                result = music.player_availability_result("media_player.kitchen", state)
                self.assertIs(result.status, PlayerAvailability.AVAILABLE if expected else PlayerAvailability.UNAVAILABLE)
                self.assertIs(result.available, expected)
                self.assertIs(music.player_available("media_player.kitchen", state), expected)
                with self.assertRaises(AttributeError):
                    setattr(result, "status", PlayerAvailability.AVAILABLE)

    def test_feedback_public_api_preserves_legacy_tuple(self):
        with patch.object(music, "_feedback_provider", return_value=("Saved", "music_feedback")):
            self.assertEqual(music.feedback(("like", None), "ha", Mock()),
                             ("Saved", "music_feedback"))

    def test_control_public_api_preserves_kwargs(self):
        with patch.object(music, "_control_provider", return_value=("Stopped", "confirmed")) as core:
            self.assertEqual(music.control(("media_stop", None), "ha", Mock(),
                                           origin="kitchen", assist=True),
                             ("Stopped", "confirmed"))
            self.assertEqual(core.call_args.kwargs["origin"], "kitchen")
            self.assertTrue(core.call_args.kwargs["assist"])

    def test_play_public_api_preserves_origin(self):
        with patch.object(music, "_play_provider", return_value=("Playing", "confirmed")) as core:
            self.assertEqual(music.play(("kitchen", "country", "spotify"), "ha", Mock(),
                                        origin="satellite"), ("Playing", "confirmed"))
            self.assertEqual(core.call_args.kwargs["origin"], "satellite")

    def test_legacy_api_accepts_typed_core_result(self):
        with patch.object(music, "_play_provider",
                          return_value=ExecutionResult("Playing", Outcome.CONFIRMED)):
            self.assertEqual(music.play(("kitchen", "country", "spotify"), "ha", Mock()),
                             ("Playing", "confirmed"))

    def test_invalid_provider_outcomes_fail_closed(self):
        for name, provider, args in (
            ("feedback", "_feedback_provider", (("like", None), "ha", Mock())),
            ("control", "_control_provider", (("media_stop", None), "ha", Mock())),
            ("play", "_play_provider", (("kitchen", "country", "spotify"), "ha", Mock())),
        ):
            with self.subTest(name=name), patch.object(music, provider,
                                                        return_value=("Done", "unknown")):
                with self.assertRaises(ValueError):
                    getattr(music, name)(*args)

    def test_unverified_is_not_upgraded_to_confirmed(self):
        with patch.object(music, "_control_provider",
                          return_value=("Could not verify", "unverified")):
            self.assertEqual(music.control(("media_stop", None), "ha", Mock())[1],
                             "unverified")


if __name__ == "__main__":
    unittest.main()
