"""HTTP message validation regression tests."""
import unittest
from request_validation import message_and_session


class RequestValidationTests(unittest.TestCase):
    def test_valid_message_is_trimmed(self):
        self.assertEqual(message_and_session({"message": "  good morning  "}),
                         ("good morning", None))

    def test_valid_session_id_is_preserved(self):
        self.assertEqual(message_and_session({"message": "hi", "session_id": "abc"}),
                         ("hi", "abc"))

    def test_missing_message_rejected(self):
        with self.assertRaises(KeyError):
            message_and_session({})

    def test_blank_message_rejected(self):
        with self.assertRaises(ValueError):
            message_and_session({"message": "  "})

    def test_overlong_message_rejected(self):
        with self.assertRaises(ValueError):
            message_and_session({"message": "a" * 1001})

    def test_maximum_length_message_accepted(self):
        self.assertEqual(len(message_and_session({"message": "a" * 1000})[0]), 1000)

    def test_non_string_message_rejected(self):
        with self.assertRaises(AttributeError):
            message_and_session({"message": 123})

    def test_overlong_session_rejected(self):
        with self.assertRaises(ValueError):
            message_and_session({"message": "hi", "session_id": "a" * 65})

    def test_non_string_session_rejected(self):
        with self.assertRaises(ValueError):
            message_and_session({"message": "hi", "session_id": 42})

    def test_maximum_session_length_accepted(self):
        self.assertEqual(message_and_session({"message": "hi", "session_id": "a" * 64})[1],
                         "a" * 64)
