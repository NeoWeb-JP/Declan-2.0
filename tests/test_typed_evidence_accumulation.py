"""Active request evidence stays typed until explicit wire/history adapters."""
from typing import Any
import unittest
from unittest.mock import Mock, patch

from action_evidence_buffer import ActionEvidenceBuffer, append_action_evidence, extend_action_evidence, evidence_value
from action_evidence_wire import action_evidence_to_wire
from execution_results import Outcome
from execution_results import ActionResult, ActionStatus, MovieLaunchStatus
from fallback_action_evidence import FallbackActionEvidence
from movie_action_evidence import MovieActionEvidence
from action_evidence_buffer import evidence_completed
from lighting_action_evidence import LightingActionEvidence, LightingActionStatus
from routine_action_evidence import RoutineActionEvidence, RoutineActionStatus
import personality_policy
import response_composition
import server
import session_turn_state
import turn_context_preparation


class TypedEvidenceAccumulationTests(unittest.TestCase):
    def test_completion_gate_preserves_each_provider_vocabulary_and_legacy_rows(self):
        rows: list[tuple[object, bool]]
        rows = [(LightingActionEvidence("Study", "turn_on", status), status in
                 {LightingActionStatus.CONFIRMED, LightingActionStatus.ALREADY_SET}) for status in LightingActionStatus]
        rows.extend((RoutineActionEvidence("Routine", status), status in
                     {RoutineActionStatus.CONFIRMED, RoutineActionStatus.ALREADY_SET}) for status in RoutineActionStatus)
        for status in ActionStatus:
            rows.extend(((ActionResult(0, "light.study", "turn_on", status), status is ActionStatus.CONFIRMED),
                         (FallbackActionEvidence("light.study", "turn_on", status), status is ActionStatus.CONFIRMED)))
        rows.extend((MovieActionEvidence("App", status, "media_player.tv", "receipt"), False) for status in MovieLaunchStatus)
        for row, completed in rows:
            with self.subTest(row=row), patch.object(type(row), "to_wire", side_effect=AssertionError("early projection")):
                self.assertIs(evidence_completed(row), completed)
        for wire_status, completed in (("confirmed", True), ("already_set", True), ("completed", True),
                                  ("sent", False), ("requested", False), ("planned", False),
                                  ("CONFIRMED", False), ("future", False), ([], False), (None, False)):
            self.assertIs(evidence_completed({"status": wire_status}), completed)
        self.assertFalse(evidence_completed(object()))

    def test_typed_sink_retains_identity_while_legacy_sink_gets_mappings(self):
        evidence = LightingActionEvidence("Study", "turn_on", LightingActionStatus.CONFIRMED, "light.study")
        legacy: list[dict[str, Any]]
        typed, legacy = ActionEvidenceBuffer(), []
        with patch.object(LightingActionEvidence, "to_wire", side_effect=AssertionError("early projection")):
            append_action_evidence(typed, evidence)
            self.assertIs(typed[0], evidence)
            self.assertIs(evidence_value(typed[0], "status"), LightingActionStatus.CONFIRMED)
        append_action_evidence(legacy, evidence)
        self.assertEqual(legacy, [evidence.to_wire()])
        self.assertEqual(action_evidence_to_wire(typed), legacy)

    def test_mixed_transfer_preserves_legacy_rows_and_typed_identity(self):
        evidence = RoutineActionEvidence("Music", RoutineActionStatus.REQUESTED, action="play", required=False)
        old = {"status": "legacy", "extra": True}
        legacy: list[dict[str, Any]]
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
             patch.object(server, 'read_ha_inventory_result', return_value=(inventory, None)), \
             patch.object(LightingActionEvidence, "to_wire", side_effect=AssertionError("early projection")):
            result = server.set_lights_result("study", "on", preview=True, action_results=steps)
        self.assertIs(result.outcome, Outcome.PREVIEW)
        self.assertIsInstance(steps[0], LightingActionEvidence)
        self.assertIs(steps[0].status, LightingActionStatus.PLANNED)

    def test_mapped_routine_completion_retains_typed_evidence(self):
        rows: list[dict[str, str]]
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
        evidence = LightingActionEvidence("Study", "turn_on", LightingActionStatus.SKIPPED, detail="unresolved")
        steps = ActionEvidenceBuffer([evidence])
        suggest = Mock(return_value=None)
        session: dict[str, Any]
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
        evidence = RoutineActionEvidence("dinner_music", RoutineActionStatus.REQUESTED, action="request_playback", required=False)
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
