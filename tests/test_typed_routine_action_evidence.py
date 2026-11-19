"""Routine evidence statuses remain distinct from verified action statuses."""
from typing import Any
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import patch

from declan.core.execution_results import Outcome
from declan.turn.routine_action_evidence import RoutineActionEvidence, RoutineActionStatus, parse_routine_actions
import server


class TypedRoutineActionEvidenceTests(unittest.TestCase):
    def test_all_legacy_statuses_roundtrip_to_plain_wire_strings(self):
        rows = [{"target": status.value, "status": status.value} for status in RoutineActionStatus]
        typed = parse_routine_actions(rows)
        self.assertEqual(len(typed), 10)
        self.assertEqual([step.to_wire() for step in typed], rows)
        self.assertTrue(all(type(step.to_wire()["status"]) is str for step in typed))
        self.assertEqual([step.to_wire() for step in server.routine_action_results_typed(rows)], rows)

    def test_only_confirmed_and_already_set_count_as_completed(self):
        for status in RoutineActionStatus:
            self.assertEqual(RoutineActionEvidence("target", status).completed,
                             status in {RoutineActionStatus.CONFIRMED, RoutineActionStatus.ALREADY_SET})

    def test_bounding_filtering_and_optional_fields_match_legacy_contract(self):
        rows = [{"target": "x" * 300, "status": "requested", "detail": "d" * 300,
                 "required": False, "action": "", "entity_id": 42, "extra": "drop"},
                {"target": "bad", "status": "unknown"}, {"target": "bad", "status": []},
                {"target": 42, "status": "confirmed"}]
        rows.extend({"target": str(index), "status": "confirmed"} for index in range(250))
        typed = parse_routine_actions(rows)
        self.assertEqual(len(typed), 197)
        self.assertEqual(typed[0].target, "x" * 240)
        self.assertEqual(typed[0].detail, "d" * 240)
        self.assertFalse(typed[0].required)
        self.assertEqual(typed[0].to_wire()["action"], "")
        self.assertNotIn("entity_id", typed[0].to_wire())
        self.assertNotIn("extra", typed[0].to_wire())

    def test_compact_mapping_and_invalid_container_compatibility(self):
        typed = parse_routine_actions({"light": "already_set", "music": "requested"})
        self.assertIs(typed[0].status, RoutineActionStatus.ALREADY_SET)
        self.assertIs(typed[1].status, RoutineActionStatus.REQUESTED)
        for invalid in (None, "steps", ({"target": "light", "status": "confirmed"},)):
            self.assertEqual(parse_routine_actions(invalid), ())
            self.assertEqual(server.routine_action_results_typed(invalid), ())

    def test_evidence_is_frozen_and_rejects_invalid_fields(self):
        evidence = RoutineActionEvidence("light", RoutineActionStatus.CONFIRMED)
        with self.assertRaises(FrozenInstanceError):
            setattr(evidence, 'status', RoutineActionStatus.REQUESTED)
        for arguments in ({"target": "light", "status": "invalid"},
                          {"target": "x" * 241, "status": "confirmed"},
                          {"target": "light", "status": "confirmed", "required": 1},
                          {"target": "light", "status": "confirmed", "detail": []}):
            with self.assertRaises(ValueError):
                RoutineActionEvidence(**arguments)

    def test_completion_consumes_typed_evidence_without_legacy_roundtrip(self):
        payload = {"schema_version": 1, "request_id": "request", "routine_id": "script.tea",
                   "outcome": "success", "steps": [{"target": "light", "status": "already_set"}]}
        steps: list[dict[str, Any]]
        steps = []
        with patch.object(server, "add_sass", side_effect=lambda reply, *_: reply):
            result, _ = server.routine_completion_result(payload, "request", "script.tea", "morning", None, steps)
        self.assertIs(result.outcome, Outcome.REPORTED_SUCCESS)
        self.assertEqual(steps, [{"target": "light", "status": "already_set"}])
        self.assertIs(type(steps[0]["status"]), str)

    def test_requested_evidence_cannot_promote_reported_success(self):
        for status in ("requested", "planned", "already_requested", "not_requested"):
            payload = {"schema_version": 1, "request_id": "request", "routine_id": "script.tea",
                       "outcome": "success", "steps": [{"target": "light", "status": status}]}
            result, _ = server.routine_completion_result(payload, "request", "script.tea", "morning", None, [])
            self.assertIs(result.outcome, Outcome.UNVERIFIED)


if __name__ == "__main__":
    unittest.main()
