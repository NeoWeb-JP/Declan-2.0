"""VoicePipeline remote operation permission regression tests."""

import unittest
from unittest.mock import Mock

from declan.voice.voicepipeline_access_http import enforce_access, requires_local_access


class VoicePipelineAccessTests(unittest.TestCase):
    def denied(self, body, *, path="/api/voicepipeline", ingress=False, ip="192.0.2.1"):
        return requires_local_access(path=path, ingress=ingress, client_ip=ip, body=body)

    def test_allowed_remote_review_operations(self):
        for body in (
            {"operation": "resolve", "action": "confirm"},
            {"operation": "resolve", "action": "assign"},
            {"operation": "resolve", "action": "dismiss"},
            {"operation": "resolve", "action": "enrol"},
            {"operation": "audio", "interaction_id": "1"},
            {"operation": "history"},
            {"operation": "correct", "interaction_id": "1", "assigned_to": "Edd",
             "expected_resolution_id": "old", "confirm": True},
        ):
            with self.subTest(body=body):
                self.assertFalse(self.denied(body))

    def test_remote_destructive_or_malformed_operations_denied(self):
        body: object
        for body in (
            None, [], {"operation": "delete"},
            {"operation": "resolve", "action": "delete"},
            {"operation": "audio", "interaction_id": "1", "delete": True},
            {"operation": "history", "clear": True},
            {"operation": "correct", "interaction_id": "1", "assigned_to": "Edd",
             "expected_resolution_id": "old", "confirm": False},
            {"operation": "correct", "interaction_id": "1", "assigned_to": "Edd",
             "expected_resolution_id": "old", "confirm": True, "extra": True},
        ):
            with self.subTest(body=body):
                self.assertTrue(self.denied(body))

    def test_local_and_ingress_bypass_remote_restriction(self):
        self.assertFalse(self.denied({"operation": "delete"}, ingress=True))
        self.assertFalse(self.denied({"operation": "delete"}, ip="127.0.0.1"))
        self.assertFalse(self.denied({"operation": "delete"}, path="/api/chat"))

    def test_denial_response(self):
        handler = Mock(path="/api/voicepipeline", client_address=("192.0.2.1", 8000))
        self.assertFalse(enforce_access(handler, {"operation": "delete"}, ingress=False))
        handler.send_json.assert_called_once_with(
            403, {"error": "This VoicePipeline action requires local access."},
        )

    def test_allowed_request_does_not_respond(self):
        handler = Mock(path="/api/voicepipeline", client_address=("192.0.2.1", 8000))
        self.assertTrue(enforce_access(handler, {"operation": "history"}, ingress=False))
        handler.send_json.assert_not_called()


if __name__ == "__main__":
    unittest.main()
