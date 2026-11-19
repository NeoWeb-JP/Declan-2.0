"""Follow-on and lighting responses retain typed evidence and voice context."""
from typing import Any
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from command_response import CommandResponse
from execution_results import ActionResult, ActionStatus, ExecutionResult, Outcome
from declan.ha import lighting_result_dispatch
import response_composition
import routine_follow_on
import routine_follow_on_dispatch


class TypedFollowOnResponseTests(unittest.TestCase):
    def setUp(self):
        self.action = ActionResult(0, "light.study", "light.turn_off", ActionStatus.CONFIRMED)
        self.original = ExecutionResult("Routine finished.", Outcome.REPORTED_SUCCESS, (self.action,))
        self.dispatch = SimpleNamespace(result=self.original, routine_follow_on=None, routine_status="Trace verified")
        self.execute = Mock()
        self.args = dict(origin_device="study", satellite="kitchen", action_results=[],
                         scope="house", execute=self.execute, parse_music=Mock(),
                         play_music=Mock(), connection=Mock(), music_inventory=Mock(),
                         handle_lighting=Mock(), last_lights=(), chained_outcome=Mock())

    def test_no_follow_on_preserves_identity_without_executor_or_legacy_adapter(self):
        with patch.object(ExecutionResult, "as_legacy_pair", side_effect=AssertionError("legacy result")):
            response = routine_follow_on_dispatch.execute_follow_on_result(self.dispatch, **self.args)
        self.assertIs(response.result, self.original)
        self.assertIsNone(response.routine_voice_result)
        self.execute.assert_not_called()

    def test_follow_on_routes_once_and_preserves_typed_response(self):
        self.dispatch.routine_follow_on = "play country"
        expected = CommandResponse(self.original, routine_voice_result=self.original)
        self.execute.return_value = expected
        response = routine_follow_on_dispatch.execute_follow_on_result(self.dispatch, **self.args)
        self.assertIs(response, expected)
        self.execute.assert_called_once()
        arguments = self.execute.call_args.kwargs
        self.assertIs(arguments["routine_result"], self.original)
        self.assertEqual(arguments["origin"], "study")
        self.assertEqual(arguments["music_origin"], "kitchen")

    def test_follow_on_rejects_untyped_executor_response(self):
        self.dispatch.routine_follow_on = "lights on"
        self.execute.return_value = ("Done", "confirmed")
        with self.assertRaises(ValueError):
            routine_follow_on_dispatch.execute_follow_on_result(self.dispatch, **self.args)

    def test_follow_on_combines_typed_action_evidence_and_keeps_original_voice(self):
        follow = ExecutionResult("Playing.", Outcome.UNVERIFIED, (
            ActionResult(1, "media_player.study", "media_player.play_media", ActionStatus.UNVERIFIED),))
        play = Mock(return_value=follow)
        with patch.object(ExecutionResult, "as_legacy_pair", side_effect=AssertionError("legacy result")):
            response = routine_follow_on.execute_result(
                "play country", routine_result=self.original, routine_status=None,
                parse_music=lambda _: "command", play_music=play, connection=lambda: "ha",
                music_inventory=Mock(), handle_lighting=Mock(), last_lights=(), origin="study",
                music_origin="kitchen", action_results=[], scope="house",
                chained_outcome=lambda *_: Outcome.PARTIAL)
        self.assertIs(response.result.outcome, Outcome.PARTIAL)
        self.assertEqual(response.result.actions, self.original.actions + follow.actions)
        self.assertIs(response.routine_voice_result, self.original)
        self.assertEqual(response.lighting_context, ())
        play.assert_called_once()

    def test_lighting_response_preserves_identity_context_and_none(self):
        dispatch = Mock(return_value=SimpleNamespace(result=self.original))
        context = Mock(return_value=("light.study",))
        arguments: dict[str, Any]
        arguments = dict(source="assist", origin_device="study", satellite=None,
                         registry_factory=Mock(), context_factory=Mock(), matches=Mock(),
                         parse_light_command=Mock(), handle_light_request=Mock(),
                         action_results=[], last_lights=(), scope="house",
                         dispatch_lighting=dispatch, confirmed_lighting_context=context)
        with patch.object(ExecutionResult, "as_legacy_pair", side_effect=AssertionError("legacy result")):
            response = lighting_result_dispatch.dispatch_lighting_response("lights off", **arguments)
        self.assertIs(response.result, self.original)
        self.assertEqual(response.lighting_context, ("light.study",))
        self.assertIs(context.call_args.args[1], Outcome.REPORTED_SUCCESS)
        dispatch.assert_called_once()
        dispatch.return_value = None
        context.reset_mock()
        self.assertIsNone(lighting_result_dispatch.dispatch_lighting_response("hello", **arguments))
        context.assert_not_called()

    def test_typed_original_voice_uses_original_outcome_and_preserves_follow_on_reply(self):
        render = Mock(return_value="Custom routine.")
        reply = response_composition.routine_reply(
            "Routine finished. Playing.", outcome=Outcome.PARTIAL,
            routine_turn=(("auto:script.tea", {}), "play country"),
            routine_voice_result=self.original, original_routine_reply="Routine finished. Playing.",
            phrase="run tea and play country", action_results=[], guest=False,
            visitor_present=False, render=render, personality=Mock())
        self.assertEqual(reply, "Custom routine. Playing.")
        self.assertIs(render.call_args.args[1], Outcome.REPORTED_SUCCESS)

    def test_response_context_rejects_invalid_lighting_and_voice_values(self):
        fields: object
        for fields in ({"lighting_context": []}, {"lighting_context": (42,)},
                       {"routine_voice_result": ("Done", "confirmed")}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                CommandResponse(self.original, **fields)


if __name__ == "__main__":
    unittest.main()
