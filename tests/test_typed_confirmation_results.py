"""Typed sensitive confirmations retain origin binding, expiry and blocking."""
from typing import Any, cast
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import Mock, patch

from confirmation_results import ConfirmationDecision, ConfirmationEvaluation, ConfirmationDecisionResult, ConfirmationTurnResult
from sensitive_confirmations import ConfirmationGate
import sensitive_confirmation_decision
import sensitive_confirmation_response
import sensitive_confirmation_turn


class TypedConfirmationResultTests(unittest.TestCase):
    def test_gate_origin_binding_one_shot_and_legacy_strings(self):
        gate = ConfirmationGate(clock=lambda: 1)
        arguments = dict(session="session", origin="kitchen", phrase="assign guests", group="guest", speaker=None)
        with patch.object(gate, "evaluate", side_effect=AssertionError("legacy gate")):
            prompted = gate.evaluate_result(**arguments)
            wrong_origin = gate.evaluate_result(**(arguments | dict(origin="study", phrase="yes", group=None)))
            confirmed = gate.evaluate_result(**(arguments | dict(phrase="yes", group=None)))
            replay = gate.evaluate_result(**(arguments | dict(phrase="yes", group=None)))
        self.assertIs(prompted.decision, ConfirmationDecision.PROMPT)
        self.assertIs(wrong_origin.decision, ConfirmationDecision.ALLOW)
        self.assertIs(confirmed.decision, ConfirmationDecision.CONFIRMED)
        self.assertEqual(confirmed.approved_phrase, "assign guests")
        self.assertIs(replay.decision, ConfirmationDecision.ALLOW)
        result = gate.evaluate(**arguments)
        self.assertEqual(result, ("prompt", None))
        self.assertIs(type(result[0]), str)

    def test_gate_expiry_and_cancellation_never_confirm(self):
        now = [0]
        gate = ConfirmationGate(clock=lambda: now[0])
        arguments = dict(session="session", origin="kitchen", phrase="assign guests", group="guest", speaker=None)
        gate.evaluate_result(**arguments)
        cancelled = gate.evaluate_result(**(arguments | dict(phrase="no", group=None)))
        self.assertIs(cancelled.decision, ConfirmationDecision.CANCELLED)
        gate.evaluate_result(**arguments)
        now[0] = 31
        expired = gate.evaluate_result(**(arguments | dict(phrase="yes", group=None)))
        self.assertIs(expired.decision, ConfirmationDecision.ALLOW)

    def test_decision_entrypoint_preserves_typed_evaluation_without_legacy_call(self):
        gate = Mock()
        expected = ConfirmationEvaluation(ConfirmationDecision.CONFIRMED, "assign guests")
        gate.evaluate_result.return_value = expected
        gate.evaluate.side_effect = AssertionError("legacy gate")
        result = sensitive_confirmation_decision.evaluate_result(
            "YES", "original", None, satellite="kitchen", origin_device="device",
            speaker=None, normalize=str.lower, guest_commands={}, confirmations=gate,
            new_session_id=lambda: "generated")
        self.assertIs(result.evaluation, expected)
        self.assertEqual(result.session_id, "generated")
        self.assertEqual(gate.evaluate_result.call_args.kwargs["origin"], "kitchen")
        self.assertEqual(gate.evaluate_result.call_args.kwargs["phrase"], "yes")
        gate.evaluate_result.assert_called_once()

    def test_turn_blocks_prompt_and_only_replaces_phrase_on_confirmed_unblocked_decision(self):
        evaluate = Mock()
        response = Mock()
        arguments: dict[str, Any]
        arguments = dict(source="assist", satellite="kitchen", origin_device=None,
                         speaker=None, evaluate=evaluate, confirmation_response=response,
                         normalize=Mock(), guest_commands={}, confirmations=Mock(),
                         record=Mock(), diagnostic_id=Mock(), log_error=Mock())
        for decision, blocking, approved in ((ConfirmationDecision.PROMPT, {"reply": "Confirm"}, False),
                                              (ConfirmationDecision.CONFIRMED, None, True),
                                              (ConfirmationDecision.CONFIRMED, {"reply": "Blocked"}, False)):
            evaluate.return_value = ConfirmationDecisionResult("session", ConfirmationEvaluation(
                decision, "approved" if decision is ConfirmationDecision.CONFIRMED else None))
            response.return_value = blocking
            result = sensitive_confirmation_turn.confirmation_turn_result("yes", "original", "session", **arguments)
            self.assertEqual(result.confirmed, approved)
            self.assertEqual(result.phrase, "approved" if approved else "original")
            self.assertIs(result.reply, blocking)
        evaluate.reset_mock()
        bypass = sensitive_confirmation_turn.confirmation_turn_result("yes", "original", None, **(arguments | {"source": "browser"}))
        self.assertFalse(bypass.confirmed)
        evaluate.assert_not_called()

    def test_confirmation_response_records_plain_outcome_once(self):
        record = Mock()
        result = sensitive_confirmation_response.confirmation_response(
            ConfirmationDecision.PROMPT, "session", source="assist", message="guests", speaker=None,
            record=record, diagnostic_id=lambda: "trace", log_error=Mock())
        self.assertIs(type(result["outcome"]), str)
        self.assertEqual(result["outcome"], "confirmation_prompt")
        record.assert_called_once()
        self.assertIs(type(record.call_args.args[4]), str)

    def test_models_reject_invalid_or_unsafe_confirmed_contracts(self):
        for decision, phrase in (("invalid", None), ("confirmed", None), ("confirmed", ""), ("allow", 42)):
            with self.assertRaises(ValueError):
                cast(Any, ConfirmationEvaluation)(decision, phrase)
        with self.assertRaises(ValueError):
            ConfirmationTurnResult("session", "approved", {"reply": "blocked"}, True)
        result = ConfirmationEvaluation(ConfirmationDecision.ALLOW)
        with self.assertRaises(FrozenInstanceError):
            setattr(result, 'decision', ConfirmationDecision.CONFIRMED)


if __name__ == "__main__":
    unittest.main()
