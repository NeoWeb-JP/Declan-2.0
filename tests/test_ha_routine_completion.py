"""Verify that HA routine acknowledgements are not confused with execution."""
import json
import unittest
from io import BytesIO
from urllib.error import HTTPError
from unittest.mock import Mock, MagicMock, patch
import script_discovery


class RoutineResultTests(unittest.TestCase):
    def run_script(self, outcome, steps=None):
        item = {"entity_id": "script.declan_local_good_morning",
                "name": "Declan - Good Morning - Shared Local Routine",
                "fields": ["request_id", "routine_id"], "safe": True}
        def open_request(request, timeout=None):
            payload = json.loads(request.data)
            self.assertIn("?return_response", request.full_url)
            self.assertEqual(payload["routine_id"], item["entity_id"])
            self.assertTrue(payload["request_id"].startswith("declan-"))
            result = {"service_response": {
                "outcome": outcome, "request_id": payload["request_id"],
                "routine_id": payload["routine_id"], "steps": steps or []}}
            response = MagicMock()
            response.status = 200
            response.read.return_value = json.dumps(result).encode()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            return response
        opener = Mock()
        opener.open.side_effect = open_request
        with patch.object(script_discovery, "discover", return_value=([item], None)):
            return script_discovery.execute(("http://ha", {}, opener), item)

    def test_personality_only_after_verified_completion(self):
        from pathlib import Path
        source = (Path(__file__).resolve().parents[1] / "server.py").read_text()
        self.assertIn('outcome == "reported_success"', source)
        self.assertIn('verified_routine or light_result is not None', source)
        self.assertIn('outcome="confirmed" if verified_routine else outcome', source)
        import personality_policy
        with patch.object(personality_policy._RANDOM, "choice", side_effect=lambda lines: lines[0]):
            success = personality_policy.decorate(
                "Good Morning completed successfully.", outcome="confirmed",
                guest=False, visitor_present=False)
            failed = personality_policy.decorate(
                "Good Morning could not be verified.", outcome="unverified",
                guest=False, visitor_present=False)
        self.assertNotEqual(success, "Good Morning completed successfully.")
        self.assertEqual(failed, "Good Morning could not be verified.")

    def test_unsupported_response_falls_back_once_without_claiming_success(self):
        item = {"entity_id": "script.declan_local_good_morning",
                "name": "Good Morning", "fields": ["request_id", "routine_id"]}
        calls = []
        def open_request(request, timeout=None):
            calls.append(request.full_url)
            if "?return_response" in request.full_url:
                raise HTTPError(request.full_url, 400, "Bad Request", {},
                                BytesIO(b'{"message":"Service does not support response data"}'))
            response = MagicMock()
            response.status = 200
            response.read.return_value = b"[]"
            return response
        opener = Mock()
        opener.open.side_effect = open_request
        with patch.object(script_discovery, "discover", return_value=([item], None)):
            reply, outcome, _ = script_discovery.execute(("http://ha", {}, opener), item)
        self.assertEqual(len(calls), 2)
        self.assertEqual(outcome, "unverified")
        self.assertIn("does not support returning", reply)

    def test_other_400_never_retries_and_exposes_reason(self):
        item = {"entity_id": "script.declan_local_good_morning",
                "name": "Good Morning", "fields": []}
        opener = Mock()
        opener.open.side_effect = HTTPError(
            "http://ha", 400, "Bad Request", {},
            BytesIO(b'{"message":"extra keys not allowed @ data"}'))
        with patch.object(script_discovery, "discover", return_value=([item], None)):
            reply, outcome, _ = script_discovery.execute(("http://ha", {}, opener), item)
        self.assertEqual(opener.open.call_count, 1)
        self.assertEqual(outcome, "failed")
        self.assertIn("extra keys not allowed", reply)

    def test_completed_steps(self):
        reply, outcome, _ = self.run_script("success", [
            {"required": True, "status": "confirmed"}])
        self.assertEqual(outcome, "reported_success")
        self.assertIn("completed successfully", reply)

    def test_unknown_is_not_success(self):
        self.assertEqual(self.run_script("unknown")[1], "unverified")

    def test_partial_is_not_success(self):
        self.assertEqual(self.run_script("partial")[1], "partial")

    def test_unconfirmed_required_step_rejects_success(self):
        self.assertEqual(self.run_script("success", [
            {"required": True, "status": "unverified"}])[1], "unverified")


if __name__ == "__main__":
    unittest.main()
