"""Discovered-script evidence preserves projection and required-step guards."""
from http_test_doubles import HTTPResponse
from typing import Any, cast
import json
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import Mock, patch

from execution_results import Outcome
from routine_action_evidence import RoutineActionEvidence, RoutineActionStatus
from declan.ha.script_action_evidence import ScriptActionEvidence, SCRIPT_ACTION_STATUSES, parse_script_actions
from declan.ha import script_discovery


class TypedScriptActionEvidenceTests(unittest.TestCase):
    def test_all_nine_provider_statuses_retain_plain_wire_values(self):
        rows = [{"target": status.value, "status": status.value, "required": False}
                for status in SCRIPT_ACTION_STATUSES]
        evidence = parse_script_actions(rows)
        self.assertEqual(len(evidence.steps), 9)
        self.assertTrue(evidence.required_steps_completed)
        self.assertEqual([step.to_wire() for step in evidence.steps], rows)
        self.assertTrue(all(type(step.to_wire()["status"]) is str for step in evidence.steps))

    def test_required_validation_extends_beyond_projection_cap(self):
        rows = [{"target": str(index), "status": "confirmed"} for index in range(200)]
        rows.append({"target": "hidden failure", "status": "requested"})
        evidence = parse_script_actions(rows)
        self.assertEqual(len(evidence.steps), 200)
        self.assertFalse(evidence.required_steps_completed)

    def test_projection_preserves_redaction_bounding_and_malformed_filtering(self):
        rows = [{"target": "t" * 300, "status": "confirmed", "action": "a" * 300,
                 "entity_id": "light.study", "required": False, "detail": "private",
                 "evidence": "private", "observed_at": "private"},
                {"target": "planned", "status": "planned", "required": False},
                {"target": "invalid", "status": []}, {"target": 42, "status": "confirmed"}]
        evidence = parse_script_actions(rows)
        self.assertFalse(evidence.required_steps_completed)
        self.assertEqual(len(evidence.steps), 1)
        wire = evidence.steps[0].to_wire()
        self.assertEqual(wire["target"], "t" * 240)
        self.assertEqual(wire["action"], "a" * 240)
        self.assertEqual(set(wire), {"target", "status", "action", "entity_id", "required"})

    def test_existing_required_flag_and_non_list_semantics_are_preserved(self):
        for required, completed in ((False, True), (0, True), (None, True), ("false", False), (True, False)):
            evidence = parse_script_actions([{"target": "light", "status": "requested", "required": required}])
            self.assertEqual(evidence.required_steps_completed, completed)
            self.assertEqual("required" in evidence.steps[0].to_wire(), type(required) is bool)
        value: object
        for value in (None, {}, "steps"):
            evidence = parse_script_actions(value)
            self.assertEqual(evidence.steps, ())
            self.assertTrue(evidence.required_steps_completed)

    def test_report_is_frozen_and_rejects_invalid_contracts(self):
        evidence = parse_script_actions([])
        with self.assertRaises(FrozenInstanceError):
            evidence.required_steps_completed = False
        for steps, completed in (([], True), (("invalid",), True), ((), 1),
                                  ((RoutineActionEvidence("light", RoutineActionStatus.PLANNED),), True)):
            with self.assertRaises(ValueError):
                cast(Any, ScriptActionEvidence)(steps, completed)

    def execute(self, outcome, steps):
        script = {"entity_id": "script.tea", "name": "Tea", "fields": []}
        response = HTTPResponse(json.dumps({"service_response": {"outcome": outcome, "steps": steps}}).encode())
        response.status = 200
        opener = Mock()
        opener.open.return_value = response
        actions: list[dict[str, Any]]
        actions = []
        with patch.object(script_discovery, "discover_result", return_value=script_discovery.DiscoveryResult(tuple([script]), None)):
            result, _ = script_discovery.execute_result(("http://ha", {}, opener), script, action_results=actions)
        opener.open.assert_called_once()
        return result, actions

    def test_claimed_success_with_unverified_required_steps_never_appends_success_evidence(self):
        rows = [{"target": str(index), "status": "confirmed"} for index in range(200)]
        rows.append({"target": "music", "status": "requested"})
        result, actions = self.execute("success", rows)
        self.assertIs(result.outcome, Outcome.UNVERIFIED)
        self.assertEqual(actions, [])

    def test_explicit_partial_and_verified_success_keep_legacy_action_projection(self):
        for outcome, status, expected in (("partial", "requested", Outcome.PARTIAL),
                                          ("success", "already_set", Outcome.REPORTED_SUCCESS)):
            result, actions = self.execute(outcome, [{"target": "light", "status": status,
                                                       "detail": "private", "required": True}])
            self.assertIs(result.outcome, expected)
            self.assertEqual(actions, [{"target": "light", "status": status, "required": True}])
            self.assertIs(type(actions[0]["status"]), str)


if __name__ == "__main__":
    unittest.main()
