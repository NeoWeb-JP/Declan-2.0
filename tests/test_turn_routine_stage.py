"""Routine selection and follow-on action regression tests."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import turn_routine_stage as stage


class RoutineStageTests(unittest.TestCase):
    def setUp(self):
        self.kwargs = dict(
            source="assist", origin_device="kitchen", satellite="sat",
            action_results=object(), scope="kitchen", last_lights=object(),
            registry_factory=object(), context_factory=object(),
            select=object(), execute=object(), follow_on_execute=object(),
            parse_music=object(), play_music=object(), connection=object(),
            music_inventory=object(), handle_lighting=object(),
            chained_outcome=object(),
        )

    def test_unmatched_routine_does_not_run_follow_on(self):
        with patch.object(stage.routine_registry_dispatch, "dispatch_routine", return_value=None), patch.object(
            stage.routine_follow_on_dispatch, "execute_follow_on_result",
        ) as follow:
            self.assertIsNone(stage.dispatch("unknown", **self.kwargs))
            follow.assert_not_called()

    def test_matched_routine_preserves_status_and_follow_on_context(self):
        routine = SimpleNamespace(routine_status="done", routine_selection="morning")
        follow = SimpleNamespace(
            result=SimpleNamespace(reply="morning", outcome="confirmed"),
            lighting_context="lights", routine_voice_result="voice",
        )
        with patch.object(stage.routine_registry_dispatch, "dispatch_routine", return_value=routine), patch.object(
            stage.routine_follow_on_dispatch, "execute_follow_on_result", return_value=follow,
        ) as execute:
            result = stage.dispatch("good morning", **self.kwargs)
            self.assertEqual((result.reply, result.outcome, result.routine_status), ("morning", "confirmed", "done"))
            self.assertEqual((result.routine_turn, result.lighting_context, result.routine_voice_result), ("morning", "lights", "voice"))
            self.assertIs(execute.call_args.args[0], routine)
            self.assertEqual(execute.call_args.kwargs["scope"], "kitchen")


if __name__ == "__main__":
    unittest.main()
