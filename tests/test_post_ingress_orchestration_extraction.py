"""Regression tests for POST ingress extraction and early exits."""
import unittest
from unittest.mock import Mock, patch

import post_ingress_orchestration
import server


class PostIngressExtractionTests(unittest.TestCase):
    def setUp(self):
        self.handler = Mock()
        self.handler.has_ingress_access.return_value = True

    def test_authentication_failure_stops_before_payload_read(self):
        with patch.object(server.post_entry_gates, "enforce", return_value=False) as gate:
            with patch.object(server.post_payload_validation, "read_authorized_body") as read:
                result = post_ingress_orchestration.prepare(self.handler, r=server)
        self.assertIsNone(result)
        gate.assert_called_once()
        read.assert_not_called()

    def test_invalid_payload_returns_validation_error(self):
        with patch.object(server.post_entry_gates, "enforce", return_value=True):
            with patch.object(server.post_payload_validation, "read_authorized_body", side_effect=ValueError("bad")):
                with patch.object(server.post_payload_validation, "send_validation_error") as send:
                    result = post_ingress_orchestration.prepare(self.handler, r=server)
        self.assertIsNone(result)
        send.assert_called_once_with(self.handler)

    def test_handled_body_route_short_circuits_before_session(self):
        with patch.object(server.post_entry_gates, "enforce", return_value=True):
            with patch.object(server.post_payload_validation, "read_authorized_body", return_value=(True, {})):
                with patch.object(server.post_body_routing, "dispatch", return_value=True):
                    with patch.object(server.post_payload_validation, "message_and_session") as session:
                        result = post_ingress_orchestration.prepare(self.handler, r=server)
        self.assertIsNone(result)
        session.assert_not_called()

    def test_valid_payload_passes_to_turn(self):
        body = {"message": "hello"}
        with patch.object(server.post_entry_gates, "enforce", return_value=True):
            with patch.object(server.post_payload_validation, "read_authorized_body", return_value=(True, body)):
                with patch.object(server.post_body_routing, "dispatch", return_value=False):
                    with patch.object(server.post_operational_routing, "dispatch_before_validation", return_value=False):
                        with patch.object(server.post_payload_validation, "message_and_session", return_value=("hello", "session")):
                            with patch.object(server.post_operational_routing, "dispatch_after_validation", return_value=False):
                                result = post_ingress_orchestration.prepare(self.handler, r=server)
        self.assertEqual(result, (body, "hello", "session"))


if __name__ == "__main__":
    unittest.main()
