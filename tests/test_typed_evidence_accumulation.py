"""Active request evidence stays typed until explicit wire/history adapters."""
import unittest
from unittest.mock import Mock, patch

from action_evidence_buffer import ActionEvidenceBuffer, append_action_evidence, extend_action_evidence, evidence_value
from action_evidence_wire import action_evidence_to_wire
from execution_results import Outcome
from lighting_action_evidence import LightingActionEvidence, LightingActionStatus
from routine_action_evidence import RoutineActionEvidence, RoutineActionStatus
import personality_policy
import response_composition
import server
import session_turn_state
import turn_context_preparation


class TypedEvidenceAccumulationTests(unittest.TestCase):
    def test_typed_sink_retains_identity_while_legacy_sink_gets_mappings(self):
        evidence = LightingActionEvidence("Study", "turn_on", "confirmed", "light.study")
        typed, legacy = ActionEvidenceBuffer(), []
        with patch.object(LightingActionEvidence, "to_wire", side_effect=AssertionError("early projection")):
            append_action_evidence(typed, evidence)
            self.assertIs(typed[0], evidence)
            self.assertIs(evidence_value(typed[0], "status"), LightingActionStatus.CONFIRMED)
        append_action_evidence(legacy, evidence)
        self.assertEqual(legacy, [evidence.to_wire()])
        self.assertEqual(action_evidence_to_wire(typed), legacy)

    def test_mixed_transfer_preserves_legacy_rows_and_typed_identity(self):
        evidence = RoutineActionEvidence("Music", "requested", action="play", required=False)
        old = {"status": "legacy", "extra": True}
        typed, legacy = ActionEvidenceBuffer(), []
        extend_action_evidence(typed, [evidence, old])
        extend_action_evidence(legacy, typed)
        self.assertIs(typed[0], evidence)
        self.assertIs(typed[1], old)
        self.assertEqual(legacy, [evidence.to_wire(), old])
        self.assertIs(legacy[1], old)

    def test_lighting_provider_does_not_project_evidence_for_active_buffer(self):
        steps = ActionEvidenceBuffer()
        inventory = [{"entity_id": "light.study", "state": "off", "attributes": {}}]
        with patch.object(server, "ha_device_connection", return_value=("http://ha", {}, Mock())), \
             patch.object(server, "read_ha_inventory", return_value=(inventory, None)), \
             patch.object(LightingActionEvidence, "to_wire", side_effect=AssertionError("early projection")):
            result = server.set_lights_result("study", "on", preview=True, action_results=steps)
        self.assertIs(result.outcome, Outcome.PREVIEW)
        self.assertIsInstance(steps[0], LightingActionEvidence)
        self.assertIs(steps[0].status, LightingActionStatus.PLANNED)

    def test_mapped_routine_completion_retains_typed_evidence(self):
        rows = [{"target": "light", "status": "already_set"}]
        payload = {"schema_version": 1, "request_id": "request", "routine_id": "script.tea", "outcome": "success", "steps": rows}
        steps = ActionEvidenceBuffer()
        with patch.object(RoutineActionEvidence, "to_wire", side_effect=AssertionError("early projection")), \
             patch.object(server, "add_sass", side_effect=lambda reply, *_: reply):
            result, _ = server.routine_completion_result(payload, "request", "script.tea", "morning", None, steps)
        self.assertIs(result.outcome, Outcome.REPORTED_SUCCESS)
        self.assertIs(steps[0].status, RoutineActionStatus.ALREADY_SET)
        self.assertEqual(action_evidence_to_wire(steps), rows)

    def test_context_and_retry_consumers_read_typed_fields_without_projection(self):
        evidence = LightingActionEvidence("Study", "turn_on", "skipped", detail="unresolved")
        steps = ActionEvidenceBuffer([evidence])
        suggest = Mock(return_value=None)
        session, reply = {}, {"reply": "Unmatched"}
        with patch.object(LightingActionEvidence, "to_wire", side_effect=AssertionError("early projection")):
            actions, _ = turn_context_preparation.prepare_turn_context(None, action_results=steps,
                light_result=True, outcome=Outcome.UNRESOLVED, scope="study", message="lights", now=1, suggestion_factory=suggest)
            session_turn_state.update_turn(session, reply, message="lights", phrase="lights", outcome=Outcome.UNRESOLVED,
                scope="study", status_target=None, information_context=None, light_result=True,
                action_results=steps, actions=actions, unmatched_reply="Unmatched", now=1)
        self.assertEqual(actions, {"turn_on"})
        self.assertEqual(session["failed_light_phrase"]["actions"], actions)
        self.assertTrue(reply["continue_conversation"])

    def test_persona_optional_music_feedback_retains_requested_semantics(self):
        evidence = RoutineActionEvidence("dinner_music", "requested", action="request_playback", required=False)
        with patch.object(RoutineActionEvidence, "to_wire", side_effect=AssertionError("early projection")):
            reply = personality_policy.dinner_music_feedback([evidence], guest=True, visitor_present=False)
        self.assertIn("requested", reply)
        self.assertNotIn("playing", reply)

    def test_general_decoration_reads_typed_status_without_promoting_planned(self):
        personality = Mock()
        personality.decorate.return_value = "Decorated"
        for name in ("_SAVAGE", "_GUEST", "_DINNER_HOME", "_DINNER_GUEST"):
            setattr(personality, name, ())
        for status, expected in ((LightingActionStatus.ALREADY_SET, "Decorated"), (LightingActionStatus.PLANNED, "Done")):
            result = response_composition.general_reply(
                "Done", outcome=Outcome.CONFIRMED, routine_reply="Done", routine_turn=None, light_result=None,
                phrase="command", action_results=[LightingActionEvidence("Study", "turn_on", status)],
                guest=False, visitor_present=False, personality=personality, lines={},
                parse_music=lambda _: None, parse_music_control=lambda _: None)
            self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()
