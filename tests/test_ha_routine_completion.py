"""Verify that HA routine acknowledgements are not confused with execution."""
import json
import unittest
from unittest.mock import Mock, patch
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
            response = Mock()
            response.status = 200
            response.read.return_value = json.dumps(result).encode()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            return response
        opener = Mock()
        opener.open.side_effect = open_request
        with patch.object(script_discovery, "discover", return_value=([item], None)):
            return script_discovery.execute(("http://ha", {}, opener), item)

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
