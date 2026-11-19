"""Final composition and persistence share one typed outcome contract."""
from typing import Any, cast
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import Mock, patch

from execution_results import Outcome
from declan.turn.turn_response import TurnResponse
from declan.turn import turn_finalization
from declan.turn import turn_persistence_orchestration
from declan.turn import turn_response_composition


class TypedFinalTurnResponseTests(unittest.TestCase):
    def arguments(self):
        return dict(lighting_context=(), scope="kitchen", response_guest_mode="off",
                    outcome=Outcome.CONFIRMED, routine_turn=None, light_result=None,
                    phrase="lights", action_results=[], guest_mode="off", visitor_present=False,
                    routine_voice_result=None, routine_status="Verified",
                    converse=Mock(return_value={"session_id": "session", "reply": "Original", "custom": "kept"}),
                    compose=Mock(return_value="Decorated"), apply_outcome_metadata=Mock(),
                    **{name: Mock() for name in ("personality", "lines", "parse_music", "parse_music_control",
                                                "render_routine", "response_category", "parse_light_command",
                                                "render_failure", "composition")})

    def test_typed_composition_keeps_outcome_without_early_metadata_serialization(self):
        arguments = self.arguments()
        result = turn_response_composition.compose_turn_result("lights", "session", "Done", **arguments)
        self.assertIs(result.outcome, Outcome.CONFIRMED)
        self.assertEqual(result.session_response["reply"], "Decorated")
        self.assertEqual(result.session_response["custom"], "kept")
        self.assertIs(arguments["compose"].call_args.kwargs["outcome"], Outcome.CONFIRMED)
        arguments["apply_outcome_metadata"].assert_not_called()
        self.assertNotIn("outcome", result.session_response)

    def test_invalid_outcome_is_rejected_before_session_or_composition_changes(self):
        arguments = self.arguments()
        arguments["outcome"] = "invalid"
        with self.assertRaises(ValueError):
            turn_response_composition.compose_turn_result("lights", "session", "Done", **arguments)
        arguments["converse"].assert_not_called()
        arguments["compose"].assert_not_called()

    def test_wire_adapter_preserves_plain_strings_extra_fields_and_original_mapping(self):
        original = {"session_id": "session", "reply": "Done", "history_saved": False}
        result = cast(Any, TurnResponse)(original, "confirmed", "Verified")
        wire = result.to_wire(turn_finalization.apply_outcome_metadata)
        self.assertIs(type(wire["outcome"]), str)
        self.assertEqual(wire["outcome"], "confirmed")
        self.assertEqual(wire["routine_status"], "Verified")
        self.assertFalse(wire["history_saved"])
        self.assertNotIn("outcome", original)
        with self.assertRaises(FrozenInstanceError):
            setattr(result, 'outcome', Outcome.FAILED)

    def test_unhandled_chat_keeps_no_outcome_and_model_validates_metadata(self):
        result = TurnResponse({"session_id": "session", "reply": "Hello"})
        self.assertIsNone(result.outcome)
        self.assertNotIn("outcome", result.to_wire())
        for payload, status in (({}, None), ({"session_id": 42, "reply": "Done"}, None),
                                ({"session_id": "session", "reply": None}, None),
                                ({"session_id": "session", "reply": "Done"}, 42)):
            with self.assertRaises(ValueError):
                cast(Any, TurnResponse)(payload, None, status)

    def test_persistence_uses_authoritative_typed_outcome_and_preserves_failure_metadata(self):
        result = TurnResponse({"session_id": "session", "reply": "Done"}, Outcome.CONFIRMED, "Verified")
        def persist(reply, **dependencies):
            self.assertIs(dependencies["outcome"], Outcome.CONFIRMED)
            self.assertEqual(dependencies["routine_status"], "Verified")
            reply.update(history_saved=False, continue_conversation=False, action_results=[{"status": "confirmed"}])
        metadata = Mock(wraps=turn_finalization.apply_outcome_metadata)
        with patch.object(turn_persistence_orchestration, "persist_turn", side_effect=persist) as finalize:
            saved = turn_persistence_orchestration.persist_turn_result(
                result, apply_outcome_metadata=metadata, outcome="failed", routine_status="Stale")
        finalize.assert_called_once()
        metadata.assert_called_once()
        self.assertIs(saved.outcome, Outcome.CONFIRMED)
        self.assertFalse(saved.to_wire()["history_saved"])
        self.assertEqual(saved.to_wire()["action_results"], [{"status": "confirmed"}])
        self.assertNotIn("history_saved", result.session_response)

    def test_persistence_rejects_legacy_mapping_before_side_effects(self):
        metadata = Mock()
        with patch.object(turn_persistence_orchestration, "persist_turn") as finalize:
            with self.assertRaises(ValueError):
                turn_persistence_orchestration.persist_turn_result({}, apply_outcome_metadata=metadata)
        metadata.assert_not_called()
        finalize.assert_not_called()


if __name__ == "__main__":
    unittest.main()
