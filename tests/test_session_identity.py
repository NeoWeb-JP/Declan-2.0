"""Shared session identity validation regressions."""
import unittest

from session_identity import valid_session_id


class SessionIdentityTests(unittest.TestCase):
    def test_valid_identifiers(self):
        self.assertTrue(valid_session_id("session"))
        self.assertTrue(valid_session_id("x" * 256))

    def test_invalid_identifiers(self):
        class CustomId(str):
            pass
        value: object
        for value in (None, "", "x" * 257, 1, True, [], {}, CustomId("session")):
            with self.subTest(value=repr(value)):
                self.assertFalse(valid_session_id(value))


if __name__ == "__main__":
    unittest.main()
