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
        self.assertEqual(server.run_custom_routine("tea")[1], "unresolved")

    def test_missing_mapping_never_dispatches(self):
        self.assertEqual(server.run_custom_routine("unknown")[1], "not_configured")

    def test_voice_selection(self):
        self.assertEqual(server.select_routine("make tea", None), ("custom:tea", {}))

    def test_verified_response_requires_matching_ids(self):
        class Opener:
            def open(self, request, timeout):
                self.payload = json.loads(request.data)
                return io.BytesIO(json.dumps({"service_response": {"request_id": self.payload["request_id"], "routine_id": self.payload["routine_id"], "outcome": "success", "steps": []}}).encode())
        opener = Opener()
        with patch.object(server, "ha_device_connection", return_value=("http://ha", {}, opener)):
            self.assertEqual(server.run_custom_routine("tea")[1], "reported_success")
        self.assertEqual(opener.payload["strength"], "strong")

    def test_unverified_response_is_not_success(self):
        class Opener:
            def open(self, request, timeout):
                return io.BytesIO(b'{"service_response":{"outcome":"success"}}')
        with patch.object(server, "ha_device_connection", return_value=("http://ha", {}, Opener())):
            self.assertEqual(server.run_custom_routine("tea")[1], "unverified")

if __name__ == "__main__":
    unittest.main()
