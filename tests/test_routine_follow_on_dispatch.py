"""Routine follow-on dispatch regression tests."""
from typing import Any
import unittest
from unittest.mock import Mock
from types import SimpleNamespace
from declan.turn.routine_follow_on_dispatch import execute_follow_on


class RoutineFollowOnDispatchTests(unittest.TestCase):
    def setUp(self):
        self.dispatch = Mock()
        self.dispatch.result.as_legacy_pair.return_value = ("routine", "confirmed")
        self.dispatch.routine_status = "completed"
        self.dispatch.routine_follow_on = None
        self.execute = Mock(return_value=SimpleNamespace(reply="chained", outcome="partial",
                         lighting_context=("lights",), routine_voice_result="voice"))
        self.actions: list[dict[str, Any]]
        self.actions = []
        self.args = dict(origin_device="bedroom", satellite="kitchen",
                         action_results=self.actions, scope="house", execute=self.execute,
                         parse_music=Mock(), play_music=Mock(), connection=Mock(),
                         music_inventory=Mock(), handle_lighting=Mock(),
                         last_lights=Mock(), chained_outcome=Mock())

    def run_dispatch(self, **kwargs):
        return execute_follow_on(self.dispatch, **(self.args | kwargs))

    def test_no_follow_on_returns_original_reply(self):
        self.assertEqual(self.run_dispatch(), ("routine", "confirmed", (), None))

    def test_no_follow_on_skips_executor(self):
        self.run_dispatch()
        self.execute.assert_not_called()

    def test_empty_follow_on_skips_executor(self):
        self.dispatch.routine_follow_on = []
        self.run_dispatch()
        self.execute.assert_not_called()

    def test_follow_on_returns_chained_context(self):
        self.dispatch.routine_follow_on = ["music"]
        self.assertEqual(self.run_dispatch(), ("chained", "partial", ("lights",), "voice"))

    def test_follow_on_called_once(self):
        self.dispatch.routine_follow_on = ["music"]
        self.run_dispatch()
        self.execute.assert_called_once()

    def test_original_reply_forwarded(self):
        self.dispatch.routine_follow_on = ["music"]
        self.run_dispatch()
        self.assertEqual(self.execute.call_args.kwargs["routine_reply"], "routine")

    def test_status_forwarded(self):
        self.dispatch.routine_follow_on = ["music"]
        self.run_dispatch()
        self.assertEqual(self.execute.call_args.kwargs["routine_status"], "completed")

    def test_lighting_origin_preference(self):
        self.dispatch.routine_follow_on = ["lights"]
        self.run_dispatch()
        self.assertEqual(self.execute.call_args.kwargs["origin"], "bedroom")

    def test_music_origin_preference(self):
        self.dispatch.routine_follow_on = ["music"]
        self.run_dispatch()
        self.assertEqual(self.execute.call_args.kwargs["music_origin"], "kitchen")

    def test_music_origin_falls_back_to_device(self):
        self.dispatch.routine_follow_on = ["music"]
        self.run_dispatch(satellite=None)
        self.assertEqual(self.execute.call_args.kwargs["music_origin"], "bedroom")

    def test_actions_reference_forwarded(self):
        self.dispatch.routine_follow_on = ["music"]
        self.run_dispatch()
        self.assertIs(self.execute.call_args.kwargs["action_results"], self.actions)

    def test_executor_exception_propagates(self):
        self.dispatch.routine_follow_on = ["music"]
        self.execute.side_effect = ValueError("failed")
        with self.assertRaises(ValueError):
            self.run_dispatch()
