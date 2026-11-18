"""Retry scope contract tests."""
import unittest
from retry_scope_validation import valid_retry_scope


class RetryScopeValidationTests(unittest.TestCase):
    def test_browser_and_assist_scopes(self):
        for scope in ("browser_voice", "browser_keyboard", "kitchen",
                      ("assist", "device1", None, None),
                      ("assist", None, "user1", "assist_satellite.kitchen")):
            with self.subTest(scope=scope):
                self.assertTrue(valid_retry_scope(scope))

    def test_hostile_assist_source_subclass_is_rejected(self):
        class HostileText(str):
            def __eq__(self, other):
                raise RuntimeError("unexpected comparison")
        self.assertFalse(valid_retry_scope((HostileText("assist"), "device", None, None)))

    def test_invalid_scopes(self):
        for scope in (None, "", "  ", "x" * 257, 42, [], {},
                      ("assist", None, None, None), ("assist", "device1"),
                      ("browser_voice", "device1", None, None),
                      ("assist", "x" * 129, None, None),
                      ("assist", 123, None, None)):
            with self.subTest(scope=scope):
                self.assertFalse(valid_retry_scope(scope))


if __name__ == "__main__":
    unittest.main()
