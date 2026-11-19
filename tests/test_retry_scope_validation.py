"""Retry scope contract tests."""
import unittest
from retry_scope_validation import assist_scope, normalize_origin_id, same_origin_scope, valid_retry_scope


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

    def test_canonical_assist_scope_factory(self):
        self.assertEqual(assist_scope("device", None, "assist_satellite.kitchen"),
                         ("assist", "device", None, "assist_satellite.kitchen"))
        self.assertEqual(assist_scope(None, "user", None),
                         ("assist", None, "user", None))
        self.assertIsNone(assist_scope(None, None, None))
        self.assertIsNone(normalize_origin_id("x" * 129))
        for scope in (assist_scope("device", None, None),
                      assist_scope(None, "user", None),
                      assist_scope(None, None, "assist_satellite.kitchen")):
            self.assertTrue(valid_retry_scope(scope))

    def test_custom_origin_subclass_is_rejected_before_comparison(self):
        class HostileText(str):
            def __eq__(self, other):
                raise RuntimeError("unexpected comparison")
        self.assertFalse(valid_retry_scope(("assist", "device", HostileText("user"), None)))
        self.assertEqual(assist_scope("device", HostileText("user"), None),
                         ("assist", "device", None, None))

    def test_same_origin_scope_requires_valid_stored_and_requested(self):
        self.assertTrue(same_origin_scope("kitchen", "kitchen"))
        self.assertTrue(same_origin_scope(("assist", "device", None, None),
                                          ("assist", "device", None, None)))
        for stored, requested in (
            ("kitchen", "bedroom"),
            (("assist", "device", None, None), ("assist", "other", None, None)),
            (("assist", None, None, None), ("assist", None, None, None)),
            ("  ", "  "),
            ("kitchen", None),
        ):
            with self.subTest(stored=stored, requested=requested):
                self.assertFalse(same_origin_scope(stored, requested))

    def test_invalid_scopes(self):
        scope: object
        for scope in (None, "", "  ", "x" * 257, 42, [], {},
                      ("assist", None, None, None), ("assist", "device1"),
                      ("browser_voice", "device1", None, None),
                      ("assist", "x" * 129, None, None),
                      ("assist", 123, None, None)):
            with self.subTest(scope=scope):
                self.assertFalse(valid_retry_scope(scope))


if __name__ == "__main__":
    unittest.main()
