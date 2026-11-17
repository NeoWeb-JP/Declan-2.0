"""Fallback diagnostic evidence stays typed without exposing redacted details."""
import json
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import Mock, patch

from action_evidence_buffer import ActionEvidenceBuffer, evidence_value
from action_evidence_wire import action_evidence_to_wire
from execution_results import ActionResult, ActionStatus, ExecutionResult, Outcome
from fallback_action_evidence import FallbackActionEvidence
from guarded_fallback_dispatch import FallbackResponse, dispatch_fallback_result


class TypedFallbackEvidenceTests(unittest.TestCase):
    def action(self, status=ActionStatus.UNVERIFIED):
        return ActionResult(0, "light.study", "light.turn_on", status, "private readback")

    def test_projection_preserves_status_and_explicit_detail_policy(self):
        for status in ActionStatus:
            for include_detail in (False, True):
                evidence = FallbackActionEvidence.from_action(self.action(status), include_detail=include_detail)
                self.assertIs(evidence.status, status)
                self.assertIs(evidence_value(evidence, "status"), status)
                self.assertEqual(evidence.detail, "private readback" if include_detail else None)
                wire = evidence.to_wire()
                self.assertEqual("detail" in wire, include_detail)
                self.assertIs(type(wire["status"]), str)
                self.assertTrue(wire["ai_generated"])
                self.assertEqual(json.loads(json.dumps(wire)), wire)

    def test_frozen_projection_rejects_untyped_actions_or_bad_policy(self):
        evidence = FallbackActionEvidence.from_action(self.action(), include_detail=False)
        with self.assertRaises(FrozenInstanceError):
            evidence.detail = "changed"
        for action, policy in (({}, False), (self.action(), 1)):
            with self.assertRaises(ValueError):
                FallbackActionEvidence.from_action(action, include_detail=policy)

    def test_dispatch_keeps_typed_evidence_identity_without_early_serialization(self):
        evidence = FallbackActionEvidence.from_action(self.action(), include_detail=False)
        execution = ExecutionResult("Cannot verify", Outcome.UNVERIFIED, (self.action(),))
        provider = Mock(return_value=FallbackResponse(execution, (evidence,)))
        rows = ActionEvidenceBuffer()
        with patch.object(FallbackActionEvidence, "to_wire", side_effect=AssertionError("early projection")):
            result = dispatch_fallback_result("lights", source="assist", exposed_entities=("light.study",),
                                               fallback_handler=provider, action_results=rows)
        self.assertIs(result, execution)
        self.assertIs(rows[0], evidence)
        provider.assert_called_once()
        self.assertNotIn("detail", action_evidence_to_wire(rows)[0])

    def test_legacy_sink_and_public_triple_remain_plain_redacted_mappings(self):
        evidence = FallbackActionEvidence.from_action(self.action(), include_detail=False)
        execution = ExecutionResult("Cannot verify", Outcome.UNVERIFIED)
        response = FallbackResponse(execution, (evidence,))
        rows = []
        dispatch_fallback_result("lights", source="assist", exposed_entities=(),
                                 fallback_handler=lambda *args, **kwargs: response, action_results=rows)
        self.assertEqual(rows, [evidence.to_wire()])
        self.assertEqual(response.as_legacy_triple(), ("Cannot verify", "unverified", rows))
        self.assertIs(type(rows[0]["status"]), str)
        self.assertNotIn("detail", rows[0])

    def test_mixed_legacy_rows_preserve_extra_fields_and_order(self):
        evidence = FallbackActionEvidence.from_action(self.action(), include_detail=True)
        legacy = {"status": "custom", "extra": "kept"}
        response = FallbackResponse(ExecutionResult("Partial", Outcome.PARTIAL), (legacy, evidence))
        triple = response.as_legacy_triple()
        self.assertIs(triple[2][0], legacy)
        self.assertEqual(triple[2][1], evidence.to_wire())


if __name__ == "__main__":
    unittest.main()
