"""Typed Music Assistant provider entrypoint and registry compatibility tests."""
import unittest
from unittest.mock import Mock, patch

import music
from command_registry import Dependencies, RequestContext, registry
from execution_results import ExecutionResult, Outcome


class MusicProviderTypedTests(unittest.TestCase):
    def test_feedback_returns_typed_outcome(self):
        with patch.object(music, "feedback", return_value=("Saved", "music_feedback")) as legacy:
            result = music.feedback_result(("like", None), "ha", Mock())
        self.assertIsInstance(result, ExecutionResult)
        self.assertIs(result.outcome, Outcome.MUSIC_FEEDBACK)
        legacy.assert_called_once()

    def test_control_preserves_origin_and_assist(self):
        with patch.object(music, "control", return_value=("Stopped", "confirmed")) as legacy:
            result = music.control_result(("media_stop", None), "ha", Mock(),
                                          origin="kitchen", read_areas=None, assist=True)
        self.assertIs(result.outcome, Outcome.CONFIRMED)
        self.assertEqual(legacy.call_args.kwargs["origin"], "kitchen")
        self.assertTrue(legacy.call_args.kwargs["assist"])

    def test_play_preserves_origin(self):
        with patch.object(music, "play", return_value=("Playing", "confirmed")) as legacy:
            result = music.play_result(("kitchen", "country", "spotify"), "ha", Mock(),
                                       origin="satellite")
        self.assertIs(result.outcome, Outcome.CONFIRMED)
        self.assertEqual(legacy.call_args.kwargs["origin"], "satellite")

    def test_typed_provider_rejects_unknown_outcome(self):
        with patch.object(music, "play", return_value=("Playing", "unknown")):
            with self.assertRaises(ValueError):
                music.play_result(("kitchen", "country", "spotify"), "ha", Mock())

    def test_typed_provider_preserves_unverified(self):
        with patch.object(music, "control", return_value=("Cannot verify", "unverified")):
            result = music.control_result(("media_stop", None), "ha", Mock())
        self.assertIs(result.outcome, Outcome.UNVERIFIED)

    def test_registry_accepts_typed_feedback_without_unwrapping(self):
        deps = Dependencies(
            parse_status=lambda *_: None, describe_status=Mock(),
            connection=lambda: "ha", inventory=Mock(), decorate=Mock(),
            guest_mode_entity="input_boolean.guest_mode",
            parse_feedback=lambda _: ("like", None),
            feedback=lambda *_: ExecutionResult("Saved", Outcome.MUSIC_FEEDBACK),
            parse_control=lambda _: ("media_stop", None),
            control=Mock(), parse_music=Mock(), play=Mock(),
            music_inventory=Mock(), areas=Mock(),
        )
        result = registry(deps).dispatch(RequestContext("like", "assist"))
        self.assertIs(result.result.outcome, Outcome.MUSIC_FEEDBACK)
        deps.control.assert_not_called()
        deps.play.assert_not_called()

    def test_registry_rejects_invalid_typed_provider_response(self):
        deps = Dependencies(
            parse_status=lambda *_: None, describe_status=Mock(),
            connection=lambda: "ha", inventory=Mock(), decorate=Mock(),
            guest_mode_entity="input_boolean.guest_mode",
            parse_feedback=lambda _: ("like", None),
            feedback=lambda *_: ("Saved", "invalid"), parse_control=Mock(),
            control=Mock(), parse_music=Mock(), play=Mock(),
            music_inventory=Mock(), areas=Mock(),
        )
        with self.assertRaises(ValueError):
            registry(deps).dispatch(RequestContext("like", "assist"))
        deps.control.assert_not_called()


if __name__ == "__main__":
    unittest.main()
