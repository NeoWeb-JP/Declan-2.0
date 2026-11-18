"""Routine follow-on response and dependency forwarding tests."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from routine_follow_on_orchestration import execute_routine_follow_on, RoutineFollowOnOutcome


class RoutineFollowOnTests(unittest.TestCase):
    def test_preserves_reply_outcome_and_context(self):
        response = SimpleNamespace(
            result=SimpleNamespace(reply="done", outcome="completed"),
            lighting_context={"room": "lounge"}, routine_voice_result="voice",
        )
        dispatch = Mock(return_value=response)
        dependencies = {
            name: Mock() for name in (
                "execute", "parse_music", "play_music", "connection",
                "music_inventory", "handle_lighting", "chained_outcome",
            )
        }
        result = execute_routine_follow_on(
            "selected-routine", origin_device="kitchen", satellite="sat",
            action_results="actions", scope="room", execute_follow_on=dispatch,
            last_lights="previous", **dependencies,
        )
        self.assertEqual(result, RoutineFollowOnOutcome(
            "done", "completed", {"room": "lounge"}, "voice",
        ))
        dispatch.assert_called_once_with(
            "selected-routine", origin_device="kitchen", satellite="sat",
            action_results="actions", scope="room", last_lights="previous",
            **dependencies,
        )

    def test_missing_optional_context_is_preserved(self):
        response = SimpleNamespace(
            result=SimpleNamespace(reply="ok", outcome="failed"),
            lighting_context=None, routine_voice_result=None,
        )
        result = execute_routine_follow_on(
            None, origin_device=None, satellite=None, action_results=None,
            scope=None, execute_follow_on=Mock(return_value=response),
            execute=None, parse_music=None, play_music=None, connection=None,
            music_inventory=None, handle_lighting=None, last_lights=None,
            chained_outcome=None,
        )
        self.assertIsNone(result.lighting_context)
        self.assertIsNone(result.routine_voice_result)
        self.assertEqual(result.outcome, "failed")


if __name__ == "__main__":
    unittest.main()
