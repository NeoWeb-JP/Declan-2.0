"""Empty script responses use exact invocation evidence without replaying actions."""
from http_test_doubles import HTTPResponse
from email.message import Message
import io
import json
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from declan.ha import script_discovery


class TraceCompletionTests(unittest.TestCase):
    def test_discovered_provider_outcome_normalization_and_unknown_values(self):
        for outcome, expected in (("SUCCESS", "reported_success"), ("partial", "partial"),
                ("failed", "failed"), ("cancelled", "cancelled"), ("started", "started"),
                ("busy", "busy"), ("unknown", "unverified"), ([], "unverified"),
                ("new_outcome", "unverified")):
            with self.subTest(outcome=outcome):
                result, calls = self.execute(data={"outcome": outcome, "steps": [{"target": "light", "status": "confirmed"}]})
                self.assertEqual(result[1], expected)
                self.assertEqual(len(calls), 1)

    def test_trace_protocol_unknown_or_malformed_status_never_claims_success(self):
        status: object
        for status in ("skipped", "unverified", "finished", "FINISHED_UNVERIFIED", [], None):
            with self.subTest(status=status):
                result, calls = self.execute(status=status)
                self.assertEqual(result[1], "unverified")
                self.assertEqual([call.get_method() for call in calls], ["POST", "GET"])

    def execute(self, status="finished_unverified", *, contexts=("context1",), expect_response=False,
                evidence_override=None, data=None, error=None):
        script = {"entity_id": "script.dinner", "name": "Dinner", "fields": []}
        changed = [{"entity_id": "script.dinner", "context": {"id": value}} for value in contexts]
        calls = []
        def open_request(request, timeout):
            calls.append(request)
            if request.get_method() == "POST":
                payload = {"service_response": {} if data is None else data, "changed_states": changed}
            else:
                if error:
                    raise error
                payload = {"entity_id": "script.dinner", "context_id": "context1", "evidence": "ha_trace",
                           "run_id": "run1", "status": status, **(evidence_override or {})}
            response = HTTPResponse(json.dumps(payload).encode())
            response.status = 200
            return response
        opener = Mock(open=open_request)
        with patch.object(script_discovery, "discover_result", return_value=script_discovery.DiscoveryResult(tuple([script]), None)):
            result = script_discovery.execute(("http://ha", {}, opener), script, expect_response=expect_response)
        return result, calls

    def test_empty_response_reports_correlated_execution_completion(self):
        result, calls = self.execute()
        self.assertEqual(result[:2], ("Routine finished.", "execution_completed"))
        self.assertIn("device results not verified", result[2])
        self.assertEqual([call.get_method() for call in calls], ["POST", "GET"])
        self.assertIn("context_id=context1", calls[1].full_url)

    def test_failures_and_partial_runs_are_not_success(self):
        for status, expected in (("partial", "partial"), ("failed", "failed"), ("cancelled", "cancelled"), ("running", "started"), ("unverified", "unverified")):
            self.assertEqual(self.execute(status)[0][1], expected)

    def test_unrelated_or_uncorrelated_trace_is_rejected(self):
        for override in ({"context_id": "other"}, {"entity_id": "script.other"}, {"run_id": ""}, {"evidence": "latest_run"}):
            self.assertEqual(self.execute(evidence_override=override)[0][1], "unverified")
        for contexts in ((), ("one", "two")):
            result, calls = self.execute(contexts=contexts)
            self.assertEqual(result[1], "unverified")
            self.assertEqual(len(calls), 1)

    def test_status_requests_still_require_spoken_summary(self):
        result, calls = self.execute(expect_response=True)
        self.assertEqual(result[1], "unverified")
        self.assertEqual(len(calls), 1)

    def test_trace_lookup_failure_never_replays_script(self):
        for error in (TimeoutError(), HTTPError("http://ha", 404, "missing", Message(), io.BytesIO(b""))):
            result, calls = self.execute(error=error)
            self.assertEqual(result[1], "unverified")
            self.assertEqual([call.get_method() for call in calls], ["POST", "GET"])

    def test_explicit_failure_remains_authoritative(self):
        result, calls = self.execute(data={"outcome": "failed"})
        self.assertEqual(result[1], "failed")
        self.assertEqual(len(calls), 1)
