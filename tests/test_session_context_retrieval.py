"""Recent session context scope and expiry regression tests."""
import unittest
from session_context_retrieval import recent_context


class SessionContextRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.previous = {
            "at": 100, "device_status_scope": "kitchen",
            "device_status_target": "light.kitchen",
            "lighting_scope": "kitchen", "lighting_context": ("light.kitchen",),
            "information_scope": "kitchen", "information_context": ("weather",),
        }

    def test_recent_matching_scope_returns_all_contexts(self):
        self.assertEqual(recent_context(self.previous, "kitchen", now=109, idle_seconds=10),
                         (("light.kitchen",), "light.kitchen", ("weather",)))

    def test_expired_context_is_ignored(self):
        self.assertEqual(recent_context(self.previous, "kitchen", now=110, idle_seconds=10),
                         ((), None, None))

    def test_different_scope_does_not_leak_context(self):
        self.assertEqual(recent_context(self.previous, "bedroom", now=101, idle_seconds=10),
                         ((), None, None))

    def test_missing_scope_does_not_leak_context(self):
        self.assertEqual(recent_context(self.previous, None, now=101, idle_seconds=10),
                         ((), None, None))

    def test_missing_session_returns_defaults(self):
        self.assertEqual(recent_context(None, "kitchen", now=101, idle_seconds=10),
                         ((), None, None))

    def test_independent_scope_per_context(self):
        self.previous["lighting_scope"] = "bedroom"
        self.assertEqual(recent_context(self.previous, "kitchen", now=101, idle_seconds=10),
                         ((), "light.kitchen", ("weather",)))

    def test_malformed_and_future_session_timestamps_cannot_restore_actions(self):
        for at in (None, "recent", True, float("nan"), float("inf"), 200):
            with self.subTest(at=repr(at)):
                previous = {**self.previous, "at": at}
                self.assertEqual(recent_context(previous, "kitchen", now=101, idle_seconds=10),
                                 ((), None, None))
        previous = dict(self.previous)
        previous.pop("at")
        self.assertEqual(recent_context(previous, "kitchen", now=101, idle_seconds=10),
                         ((), None, None))

    def test_non_mapping_previous_context_is_ignored(self):
        for previous in ("hello", [], 123):
            with self.subTest(previous=repr(previous)):
                self.assertEqual(recent_context(previous, "kitchen", now=101, idle_seconds=10),
                                 ((), None, None))

    def test_missing_context_values_use_defaults(self):
        self.assertEqual(recent_context({"at": 100, "lighting_scope": "kitchen"},
                                        "kitchen", now=101, idle_seconds=10),
                         ((), None, None))
