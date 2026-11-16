"""Mapped routine execution contract tests."""
import io
import json
import unittest
from unittest.mock import patch
import server

class CustomRoutineTests(unittest.TestCase):
    def setUp(self):
        self.mapping = {"tea": {"script": "script.make_tea", "phrases": ["make tea"], "fields": {"strength": "strong"}, "sensitive": False}}
        self.enterContext(patch.object(server.routine_registry, "load", return_value=self.mapping))
        self.enterContext(patch.object(server.routine_registry, "match", side_effect=lambda phrase: ("tea", self.mapping["tea"]) if phrase == "make tea" else None))
        self.opener = self.enterContext(patch.object(server, "ha_device_connection")).return_value = None

    def test_sensitive_mapping_fails_closed(self):
        self.mapping["tea"]["sensitive"] = True
        self.assertEqual(server.run_custom_routine("tea")[1], "not_configured")

    def test_sensitive_gate_requires_confirmation_not_voice_id(self):
        import sensitive_confirmations
        self.mapping["tea"]["sensitive"] = True
        group = sensitive_confirmations.sensitive_group("make tea", (("custom:tea", {}), None), {}, {})
        self.assertEqual(group, "custom:tea")
        gate = sensitive_confirmations.ConfirmationGate()
        with patch.object(sensitive_confirmations, "trusted_speaker", return_value=True):
            decision, _ = gate.evaluate(session="test", origin="satellite", phrase="make tea", group=group, speaker={"name": "Jaco", "confidence": 1.0})
        self.assertEqual(decision, "prompt")
        decision, phrase = gate.evaluate(session="test", origin="satellite", phrase="yes", group=None, speaker=None)
        self.assertEqual((decision, phrase), ("confirmed", "make tea"))

    def test_missing_mapping_never_dispatches(self):
        self.assertEqual(server.run_custom_routine("unknown")[1], "not_configured")

    def test_voice_selection(self):
        script = {"entity_id": "script.make_tea", "name": "Make Tea", "safe": True}
        with patch.object(server, "ha_device_connection", return_value=("url", {}, object())), \
             patch.object(server.script_discovery, "discover", return_value=([script], None)):
            self.assertEqual(server.select_routine("make tea", None), ("auto:script.make_tea", {}))

    def test_verified_response_requires_matching_ids(self):
        class Opener:
            def open(self, request, timeout):
                self.payload = json.loads(request.data)
                return io.BytesIO(json.dumps({"service_response": {"request_id": self.payload["request_id"], "routine_id": self.payload["routine_id"], "outcome": "success", "steps": [{"target": "tea", "status": "confirmed"}]}}).encode())
        opener = Opener()
        with patch.object(server, "ha_device_connection", return_value=("http://ha", {}, opener)):
            self.assertEqual(server.run_custom_routine("tea")[1], "reported_success")
        self.assertEqual(opener.payload["strength"], "strong")

    def test_stop_reports_request_not_completed_rollback(self):
        class Opener:
            def open(self, request, timeout):
                self.path = request.full_url
                return io.BytesIO(b"[]")
        opener = Opener()
        with patch.object(server, "ha_device_connection", return_value=("http://ha", {}, opener)):
            with server.track_routine("tea", "script.make_tea"):
                reply, outcome, _ = server.stop_pending_routines()
        self.assertIn("Cancellation requested", reply)
        self.assertIn("not rolled back", reply)
        self.assertEqual(outcome, "unverified")
        self.assertTrue(opener.path.endswith("/api/services/script/turn_off"))

    def test_unverified_response_is_not_success(self):
        class Opener:
            def open(self, request, timeout):
                return io.BytesIO(b'{"service_response":{"outcome":"success"}}')
        with patch.object(server, "ha_device_connection", return_value=("http://ha", {}, Opener())):
            self.assertEqual(server.run_custom_routine("tea")[1], "unverified")

if __name__ == "__main__":
    unittest.main()
