"""Turn response composition contract tests."""
from typing import Any
import unittest
from unittest.mock import Mock
from declan.turn.turn_response_composition import compose_turn_response


class TurnResponseCompositionTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.converse = Mock(side_effect=self.make_reply)
        self.compose = Mock(side_effect=self.make_composition)
        self.metadata = Mock(side_effect=self.apply_metadata)
        self.dependencies = {name: Mock() for name in (
            "personality", "lines", "parse_music", "parse_music_control",
            "render_routine", "response_category", "parse_light_command",
            "render_failure", "composition")}

    def make_reply(self, *args, **kwargs):
        self.events.append("converse")
        return {"reply": "original", "session_id": "abc"}

    def make_composition(self, *args, **kwargs):
        self.events.append("compose")
        return "decorated"

    def apply_metadata(self, reply, **kwargs):
        self.events.append("metadata")
        reply["outcome"] = kwargs["outcome"]

    def run_turn(self, **overrides):
        args: dict[str, Any]
        args = dict(lighting_context=("light.kitchen",), scope="kitchen",
            response_guest_mode="off", outcome="confirmed", routine_turn=None,
            light_result=None, phrase="lights on", action_results=[],
            guest_mode="off", visitor_present=False, routine_voice_result=None,
            routine_status="ok", converse=self.converse, compose=self.compose,
            apply_outcome_metadata=self.metadata, **self.dependencies)
        args.update(overrides)
        return compose_turn_response("lights on", "abc", "done", **args)

    def test_returns_composed_reply(self):
        self.assertEqual(self.run_turn()["reply"], "decorated")

    def test_outcome_metadata_applied(self):
        self.assertEqual(self.run_turn()["outcome"], "confirmed")

    def test_execution_order(self):
        self.run_turn()
        self.assertEqual(self.events, ["converse", "compose", "metadata"])

    def test_conversation_arguments(self):
        self.run_turn()
        self.converse.assert_called_once_with("lights on", "abc", "done",
            lighting_context=("light.kitchen",), scope="kitchen", guest_mode="off")

    def test_composition_receives_conversation_text(self):
        self.run_turn()
        self.assertEqual(self.compose.call_args.args, ("original",))

    def test_guest_flags_independent(self):
        self.run_turn(guest_mode="on", response_guest_mode="off")
        self.assertTrue(self.compose.call_args.kwargs["guest"])
        self.assertFalse(self.compose.call_args.kwargs["response_guest"])

    def test_response_guest_flag(self):
        self.run_turn(response_guest_mode="guest")
        self.assertTrue(self.compose.call_args.kwargs["response_guest"])

    def test_action_results_forwarded_by_reference(self):
        steps = [{"action": "on"}]
        self.run_turn(action_results=steps)
        self.assertIs(self.compose.call_args.kwargs["action_results"], steps)

    def test_dependencies_forwarded(self):
        self.run_turn()
        for name, value in self.dependencies.items():
            self.assertIs(self.compose.call_args.kwargs[name], value)

    def test_metadata_status_forwarded(self):
        self.run_turn(routine_status="failed")
        self.metadata.assert_called_once()
        self.assertEqual(self.metadata.call_args.kwargs["routine_status"], "failed")

    def test_light_result_forwarded(self):
        self.run_turn(light_result=("on", "confirmed"))
        self.assertEqual(self.compose.call_args.kwargs["light_result"], ("on", "confirmed"))
