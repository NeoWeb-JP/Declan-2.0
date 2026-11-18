"""Regression tests for bounded POST JSON parsing."""

import io
import unittest
from unittest.mock import Mock

from post_payload_http import max_json_body_bytes, read_json_body


class PostPayloadHttpTests(unittest.TestCase):
    def test_route_limits(self):
        self.assertEqual(max_json_body_bytes("/api/native/routine-responses"), 131072)
        self.assertEqual(max_json_body_bytes("/api/voice-profiles"), 450000)
        self.assertEqual(max_json_body_bytes("/api/settings/import"), 196608)
        for path in ("/api/assist/history", "/api/assist", "/api/chat"):
            self.assertEqual(max_json_body_bytes(path), 65536)
        self.assertEqual(max_json_body_bytes("/api/settings/ai"), 8192)

    def test_valid_json(self):
        handler = Mock(path="/api/chat")
        handler.headers.get.return_value = "13"
        handler.rfile = io.BytesIO(b'{"text":"hi"}')
        self.assertEqual(read_json_body(handler), {"text": "hi"})

    def test_zero_negative_oversized_and_invalid_length(self):
        for length in ("0", "-1", "65537", "not-a-number"):
            with self.subTest(length=length):
                handler = Mock(path="/api/chat")
                handler.headers.get.return_value = length
                handler.rfile = io.BytesIO(b'{}')
                with self.assertRaises(ValueError):
                    read_json_body(handler)

    def test_invalid_json(self):
        handler = Mock(path="/api/settings/ai")
        handler.headers.get.return_value = "1"
        handler.rfile = io.BytesIO(b'{')
        with self.assertRaises(ValueError):
            read_json_body(handler)

    def test_large_routine_response_body(self):
        payload = b'{"responses":"' + b"x" * 100000 + b'"}'
        handler = Mock(path="/api/native/routine-responses")
        handler.headers.get.return_value = str(len(payload))
        handler.rfile = io.BytesIO(payload)
        self.assertEqual(len(read_json_body(handler)["responses"]), 100000)


if __name__ == "__main__":
    unittest.main()
