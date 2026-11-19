"""Provider vocabulary is interpreted before dispatch and completion decisions."""
import unittest
from unittest.mock import patch

import server
from execution_results import Outcome
from script_provider_results import ScriptProviderResult, ScriptReportedOutcome, TraceProviderOutcome, parse_trace_outcome
from script_provider_results import ScriptReason
from script_provider_results import CorrelatedTraceResult


class ScriptProviderResultTests(unittest.TestCase):
    def test_correlated_trace_results_preserve_statuses_and_metadata_guards(self):
        evidence = {"entity_id": "script.tea", "context_id": "context", "evidence": "ha_trace", "run_id": "r" * 200}
        for status in (*TraceProviderOutcome, "future", "FINISHED_UNVERIFIED", None, []):
            with self.subTest(status=status):
                result = CorrelatedTraceResult.parse({**evidence, "status": status},
                    entity_id="script.tea", context_id="context")
                assert result is not None
                self.assertIs(result.status, status if isinstance(status, TraceProviderOutcome) else None)
                self.assertEqual(result.detail, "HA trace " + "r" * 128 + "; device results not verified.")
                with self.assertRaises(AttributeError):
                    setattr(result, "status", TraceProviderOutcome.FAILED)
        for key, value in (("entity_id", "script.other"), ("context_id", "other"), ("evidence", "other"),
                           ("run_id", ""), ("run_id", 1), ("run_id", None)):
            with self.subTest(key=key, value=value):
                self.assertIsNone(CorrelatedTraceResult.parse({**evidence, key: value},
                    entity_id="script.tea", context_id="context"))
        payload: object
        for payload in (None, [], "ha_trace", {}):
            self.assertIsNone(CorrelatedTraceResult.parse(payload, entity_id="script.tea", context_id="context"))

    def test_reason_codes_are_typed_exact_and_cannot_override_other_outcomes(self):
        for reason in ScriptReason:
            for outcome in ScriptReportedOutcome:
                with self.subTest(reason=reason, outcome=outcome):
                    result = ScriptProviderResult.parse(outcome.value.upper(), normalize=True, reason=reason.value)
                    self.assertIs(result.reason, reason)
                    self.assertIs(result.guard_reason, reason if outcome in
                                  {ScriptReportedOutcome.UNKNOWN, ScriptReportedOutcome.BUSY} else None)
                    with self.assertRaises(AttributeError):
                        setattr(result, "reason", None)
            raw: object
            for raw in (reason.value.upper(), " " + reason.value, [], {}, None, "future_reason"):
                self.assertIsNone(ScriptProviderResult.parse("busy", reason=raw).guard_reason)
        self.assertIsNone(ScriptProviderResult.parse("future_outcome", reason="screen_moving").guard_reason)

    def test_supported_outcomes_have_explicit_execution_interpretations(self):
        expected = {"success": Outcome.REPORTED_SUCCESS, "partial": Outcome.PARTIAL,
                    "failed": Outcome.FAILED, "cancelled": Outcome.CANCELLED,
                    "unknown": Outcome.UNVERIFIED, "started": Outcome.STARTED, "busy": Outcome.BUSY}
        for value, outcome in expected.items():
            with self.subTest(value=value):
                parsed = ScriptProviderResult.parse(value)
                self.assertIs(parsed.outcome, ScriptReportedOutcome(value))
                self.assertIs(parsed.execution_outcome, outcome)
                with self.assertRaises(AttributeError):
                    setattr(parsed, "outcome", None)

    def test_normalization_is_explicit_and_unknown_values_stay_unverified(self):
        self.assertIsNone(ScriptProviderResult.parse("SUCCESS").outcome)
        self.assertIs(ScriptProviderResult.parse("SUCCESS", normalize=True).outcome, ScriptReportedOutcome.SUCCESS)
        value: object
        for value in (None, [], {}, 1, "new_outcome", " success "):
            for normalize in (False, True):
                self.assertIsNone(ScriptProviderResult.parse(value, normalize=normalize).outcome)
                self.assertIs(ScriptProviderResult.parse(value, normalize=normalize).execution_outcome, Outcome.UNVERIFIED)
        for status in TraceProviderOutcome:
            self.assertIs(parse_trace_outcome(status.value), status)
        for value in (None, [], {}, "finished", "FINISHED_UNVERIFIED"):
            self.assertIsNone(parse_trace_outcome(value))

    def test_mapped_completion_retains_required_step_adjustments(self):
        for outcome, statuses, expected in (("success", ["confirmed"], Outcome.REPORTED_SUCCESS),
                ("success", ["confirmed", "failed"], Outcome.PARTIAL),
                ("success", ["failed"], Outcome.UNVERIFIED),
                ("partial", ["failed"], Outcome.UNVERIFIED),
                ("failed", ["confirmed"], Outcome.PARTIAL),
                ("failed", ["failed"], Outcome.FAILED),
                ("busy", [], Outcome.BUSY), ("SUCCESS", ["confirmed"], Outcome.UNVERIFIED),
                ([], [], Outcome.UNVERIFIED), ("cancelled", [], Outcome.UNVERIFIED)):
            with self.subTest(outcome=outcome, statuses=statuses), patch.object(server, "add_sass", side_effect=lambda reply, *args: reply):
                payload = {"schema_version": 1, "request_id": "request", "routine_id": "routine", "outcome": outcome,
                           "steps": [{"target": str(index), "status": status} for index, status in enumerate(statuses)]}
                result, _ = server.routine_completion_result(payload, "request", "routine", "morning", None, [])
                self.assertIs(result.outcome, expected)
