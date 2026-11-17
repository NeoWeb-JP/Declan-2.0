"""Lighting evidence retains planning, completion and compatibility semantics."""
import io
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import Mock, patch

from execution_results import ExecutionResult, Outcome
from lighting_action_evidence import LightingActionEvidence, LightingActionStatus, confirmed_lighting_entities
from lighting_context_finalization import confirmed_lighting_context
import server


class TypedLightingActionEvidenceTests(unittest.TestCase):
    def test_skipped_lighting_aggregation_retains_typed_outcomes_and_order(self):
        inventory = [{"entity_id": "light.study", "state": "on", "attributes": {"friendly_name": "Study"}},
                     {"entity_id": "light.hall", "state": "unavailable", "attributes": {"friendly_name": "Hall"}}]
        for name, expected in (("missing and hall", Outcome.UNRESOLVED),
                ("hall and missing", Outcome.UNAVAILABLE), ("study and missing", Outcome.PARTIAL),
                ("study", Outcome.CONFIRMED)):
            with self.subTest(name=name), \
                 patch.object(server, "ha_device_connection", return_value=("http://ha", {}, Mock())), \
                 patch.object(server, 'read_ha_inventory_result', return_value=(inventory, None)), \
                 patch.object(server, "read_ha_areas", return_value={}), \
                 patch.object(server, "set_switch_as_light_result", return_value=None), \
                 patch.object(server, "add_sass", side_effect=lambda reply, *_: reply), \
                 patch.object(server, "ExecutionResult", wraps=ExecutionResult) as model:
                result = server.set_lights_result(name, "on")
            self.assertIs(result.outcome, expected)
            self.assertTrue(all(isinstance(call.args[1], Outcome) for call in model.call_args_list))
            if "missing" in name:
                self.assertIn("couldn't find", result.reply)
            self.assertIs(type(result.as_legacy_pair()[1]), str)

    def test_all_six_statuses_roundtrip_without_promoting_planned_actions(self):
        for status in LightingActionStatus:
            evidence = LightingActionEvidence("Study", "turn_on", status, "light.study", "detail")
            wire = evidence.to_wire()
            self.assertIs(type(wire["status"]), str)
            self.assertEqual(wire, {"target": "Study", "action": "turn_on", "status": status.value,
                                    "entity_id": "light.study", "detail": "detail"})
            self.assertEqual(evidence.completed, status in {LightingActionStatus.CONFIRMED, LightingActionStatus.ALREADY_SET})

    def test_evidence_is_frozen_validated_and_preserves_existing_text(self):
        evidence = LightingActionEvidence("t" * 300, "turn_on", "confirmed", detail="")
        self.assertEqual(evidence.to_wire()["target"], "t" * 300)
        self.assertEqual(evidence.to_wire()["detail"], "")
        self.assertNotIn("entity_id", evidence.to_wire())
        with self.assertRaises(FrozenInstanceError):
            evidence.status = LightingActionStatus.PLANNED
        for fields in ({"status": "requested"}, {"target": 42}, {"action": None},
                       {"entity_id": []}, {"detail": 42}):
            with self.assertRaises(ValueError):
                LightingActionEvidence(**(dict(target="Study", action="turn_on", status="confirmed") | fields))

    def test_follow_up_selection_accepts_typed_and_legacy_evidence_in_order(self):
        steps = [LightingActionEvidence("Study", "turn_on", "confirmed", "light.study"),
                 {"status": "already_set", "entity_id": "light.kitchen"},
                 {"status": "confirmed", "entity_id": "light.study"},
                 LightingActionEvidence("Hall", "turn_on", "planned", "light.hall"),
                 {"status": "unverified", "entity_id": "light.bedroom"},
                 {"status": "confirmed", "entity_id": None}, {}, "invalid"]
        self.assertEqual(confirmed_lighting_entities(steps), ("light.study", "light.kitchen"))

    def test_context_retains_scope_preview_failure_and_cap_guards(self):
        step = LightingActionEvidence("Study", "turn_on", "confirmed", "light.study")
        self.assertEqual(confirmed_lighting_context("lights on", Outcome.CONFIRMED, "study", [step]), ("light.study",))
        for phrase, outcome, scope, rows in (("preview lights on", Outcome.CONFIRMED, "study", [step]),
                                             ("lights on", Outcome.UNVERIFIED, "study", [step]),
                                             ("lights on", Outcome.CONFIRMED, None, [step]),
                                             ("lights on", Outcome.CONFIRMED, "study", [step] * 200)):
            self.assertEqual(confirmed_lighting_context(phrase, outcome, scope, rows), ())

    def test_provider_constructs_typed_planned_and_already_set_evidence(self):
        inventory = [{"entity_id": "light.study", "state": "off", "attributes": {}}]
        for desired, preview, expected in (("on", True, LightingActionStatus.PLANNED),
                                           ("off", False, LightingActionStatus.ALREADY_SET)):
            opener = Mock()
            steps = []
            with patch.object(server, "ha_device_connection", return_value=("http://ha", {}, opener)), \
                 patch.object(server, 'read_ha_inventory_result', return_value=(inventory, None)), \
                 patch.object(server, "read_ha_areas", return_value={}), \
                 patch.object(server, "add_sass", side_effect=lambda reply, *_: reply), \
                 patch.object(server, "LightingActionEvidence", wraps=LightingActionEvidence) as model:
                server.set_lights_result("study", desired, preview=preview, action_results=steps)
            self.assertIs(model.call_args.args[2], expected)
            self.assertEqual(steps[0]["status"], expected.value)
            self.assertIs(type(steps[0]["status"]), str)
            opener.open.assert_not_called()

    def test_lighting_evidence_cap_prevents_additional_rows(self):
        inventory = [{"entity_id": "light.study", "state": "off", "attributes": {}}]
        steps = [{"status": "planned"}] * 200
        with patch.object(server, "ha_device_connection", return_value=("http://ha", {}, Mock())), \
             patch.object(server, 'read_ha_inventory_result', return_value=(inventory, None)), \
             patch.object(server, "LightingActionEvidence", wraps=LightingActionEvidence) as model:
            server.set_lights_result("study", "on", preview=True, action_results=steps)
        self.assertEqual(len(steps), 200)
        model.assert_not_called()

    def test_marked_switch_emits_verified_typed_evidence_once(self):
        row = {"entity_id": "switch.garden", "state": "off", "attributes": {
            "friendly_name": "Garden light", "declan_as_light": True}}
        opener = Mock()
        opener.open.side_effect = [io.BytesIO(b'[]'), io.BytesIO(b'{"state":"on"}')]
        steps = []
        with patch.object(server, "LightingActionEvidence", wraps=LightingActionEvidence) as model:
            result = server.set_switch_as_light_result("garden light", "on", [row], ("http://ha", {}, opener), action_results=steps)
        self.assertIs(result.outcome, Outcome.CONFIRMED)
        self.assertIs(model.call_args.args[2], LightingActionStatus.CONFIRMED)
        self.assertEqual(opener.open.call_count, 2)
        self.assertEqual(steps, [{"target": "garden light", "action": "turn_on", "status": "confirmed", "entity_id": "switch.garden"}])


if __name__ == "__main__":
    unittest.main()
