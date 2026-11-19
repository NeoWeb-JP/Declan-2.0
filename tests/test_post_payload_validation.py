"""POST body parsing and authorization ordering regression tests."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import post_payload_validation


class PostPayloadValidationTests(unittest.TestCase):
    def setUp(self):
        self.handler = SimpleNamespace(path="/api/chat")

    def test_authorized_body_is_returned_unchanged(self):
        body = {"message": "hello"}
        with patch.object(post_payload_validation.post_payload_http, "read_json_body", return_value=body) as read, \
             patch.object(post_payload_validation.voicepipeline_access_http, "enforce_access", return_value=True) as gate:
            self.assertIs(post_payload_validation.read_authorized_body(self.handler, ingress=True), body)
        read.assert_called_once_with(self.handler)
        gate.assert_called_once_with(self.handler, body, ingress=True)

    def test_denied_body_is_not_dispatched(self):
        body = {"action": "delete"}
        with patch.object(post_payload_validation.post_payload_http, "read_json_body", return_value=body), \
             patch.object(post_payload_validation.voicepipeline_access_http, "enforce_access", return_value=False):
            self.assertIsNone(post_payload_validation.read_authorized_body(self.handler, ingress=False))

    def test_parsing_error_does_not_bypass_authorization(self):
        with patch.object(post_payload_validation.post_payload_http, "read_json_body", side_effect=ValueError("invalid")), \
             patch.object(post_payload_validation.voicepipeline_access_http, "enforce_access") as gate:
            with self.assertRaises(ValueError):
                post_payload_validation.read_authorized_body(self.handler, ingress=False)
        gate.assert_not_called()

    def test_message_validation_preserves_result_and_exception(self):
        with patch.object(post_payload_validation.request_validation, "message_and_session", return_value=("hi", "s")) as validate:
            self.assertEqual(post_payload_validation.message_and_session({"message": "hi"}), ("hi", "s"))
        validate.assert_called_once_with({"message": "hi"})
        with patch.object(post_payload_validation.request_validation, "message_and_session", side_effect=ValueError("bad")):
            with self.assertRaises(ValueError):
                post_payload_validation.message_and_session({})

    def test_validation_error_uses_existing_response_contract(self):
        with patch.object(post_payload_validation.post_validation_errors_http, "send_validation_error") as error:
            post_payload_validation.send_validation_error(self.handler)
        error.assert_called_once_with(self.handler)


if __name__ == "__main__":
    unittest.main()
