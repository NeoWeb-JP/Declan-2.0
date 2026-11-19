"""Typed outcome contract regression tests for provider and follow-on boundaries."""
from typing import Any
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import Mock, patch

from execution_results import ExecutionResult, Outcome
from declan.music.music_provider_result import music_execution_result
from routine_follow_on import FollowOnResult, execute
from routine_follow_on import execute_result
import routine_follow_on


class TypedBoundaryTests(unittest.TestCase):
    def test_missing_follow_on_results_are_constructed_typed_without_legacy_roundtrips(self):
        original_init = ExecutionResult.__post_init__

        def require_enum(result):
            self.assertIsInstance(result.outcome, Outcome)
            original_init(result)

        for phrase, fragment in (("play nonsense", "Tell me where to play the music."),
                                 ("turn on mystery", "couldn't understand the lighting command")):
            with self.subTest(phrase=phrase):
                routine = ExecutionResult("Routine completed.", Outcome.EXECUTION_COMPLETED)
                play, connection = Mock(), Mock()
                lighting = Mock(return_value=None)
                combine = Mock(return_value=Outcome.PARTIAL)
                with patch.object(ExecutionResult, "__post_init__", require_enum), \
                     patch.object(routine_follow_on, "music_execution_result", side_effect=AssertionError("legacy fallback")):
                    result = execute_result(phrase, routine_result=routine, routine_status=None,
                        parse_music=lambda _: None, play_music=play, connection=connection,
                        music_inventory=Mock(), handle_lighting=lighting, last_lights=None,
                        origin="kitchen", music_origin=None, action_results=[], scope="kitchen",
                        chained_outcome=combine)
                self.assertIs(result.result.outcome, Outcome.PARTIAL)
                self.assertIs(result.routine_voice_result, routine)
                self.assertIn(fragment, result.result.reply)
                self.assertEqual(result.lighting_context, ())
                combine.assert_called_once_with(Outcome.EXECUTION_COMPLETED, Outcome.UNRESOLVED)
                self.assertIs(combine.call_args.args[1], Outcome.UNRESOLVED)
                play.assert_not_called()
                connection.assert_not_called()
                if phrase.startswith("play "):
                    lighting.assert_not_called()
                else:
                    lighting.assert_called_once()

    def test_music_legacy_pair_is_typed(self):
        result = music_execution_result(("Playing", "confirmed"))
        self.assertIs(result.outcome, Outcome.CONFIRMED)
        self.assertEqual(result.as_legacy_pair(), ("Playing", "confirmed"))

    def test_music_provider_existing_typed_result_is_preserved(self):
        result = ExecutionResult("Playing", Outcome.CONFIRMED)
        self.assertIs(music_execution_result(result), result)

    def test_music_rejects_unknown_outcome(self):
        with self.assertRaises(ValueError):
            music_execution_result(("Playing", "made_up"))

    def test_music_rejects_malformed_result(self):
        for value in (None, "confirmed", (), ("reply",), ("reply", "confirmed", "extra")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                music_execution_result(value)

    def test_music_rejects_non_string_reply(self):
        with self.assertRaises(ValueError):
            music_execution_result((None, "confirmed"))

    def test_follow_on_result_is_frozen_and_typed(self):
        result = FollowOnResult("Done", Outcome.CONFIRMED, (), ("Routine", "confirmed"))
        self.assertIs(result.outcome, Outcome.CONFIRMED)
        with self.assertRaises(FrozenInstanceError):
            setattr(result, 'outcome', Outcome.FAILED)

    def test_music_follow_on_preserves_origin_and_voice_result(self):
        play = Mock(return_value=("Playing", "confirmed"))
        result = execute(
            "play country", routine_reply="Routine done",
            routine_outcome="confirmed", routine_status=None,
            parse_music=lambda _: ("country",), play_music=play,
            connection=lambda: "ha", music_inventory=Mock(),
            handle_lighting=Mock(), last_lights=None,
            origin="kitchen", music_origin="satellite",
            action_results=[], scope="kitchen",
            chained_outcome=lambda _, follow: follow,
        )
        self.assertIs(result.outcome, Outcome.CONFIRMED)
        self.assertEqual(result.routine_voice_result, ("Routine done", "confirmed"))
        self.assertEqual(play.call_args.kwargs["origin"], "satellite")

    def test_lighting_follow_on_preserves_action_history(self):
        steps: list[dict[str, Any]]
        steps = []
        result = execute(
            "turn kitchen lights on", routine_reply="Routine done",
            routine_outcome="confirmed", routine_status=None,
            parse_music=Mock(), play_music=Mock(),
            connection=Mock(), music_inventory=Mock(),
            handle_lighting=lambda _, **kw: (
                kw["action_results"].append({"entity_id": "light.kitchen", "status": "confirmed"})
                or ("Lights on", "confirmed")
            ),
            last_lights=None, origin="kitchen", music_origin=None,
            action_results=steps, scope="kitchen",
            chained_outcome=lambda _, follow: follow,
        )
        self.assertIs(result.outcome, Outcome.CONFIRMED)
        self.assertEqual(result.lighting_context, ("light.kitchen",))
        self.assertEqual(steps[0]["entity_id"], "light.kitchen")

    def test_invalid_music_follow_on_outcome_rejected(self):
        with self.assertRaises(ValueError):
            execute(
                "play country", routine_reply="Routine", routine_outcome="confirmed",
                routine_status=None, parse_music=lambda _: ("country",),
                play_music=lambda *_args, **_kw: ("Playing", "unknown_result"),
                connection=lambda: "ha", music_inventory=Mock(),
                handle_lighting=Mock(), last_lights=None, origin=None,
                music_origin=None, action_results=[], scope=None,
                chained_outcome=lambda _, follow: follow,
            )


if __name__ == "__main__":
    unittest.main()
