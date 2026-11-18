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

    def test_malformed_scope_does_not_restore_context(self):
        for scope in ("", "  ", "x" * 257, 42, [],
                      ("assist", None, None, None),
                      ("assist", "device"), ("assist", "x" * 129, None, None)):
            with self.subTest(scope=repr(scope)):
                previous = {**self.previous, "device_status_scope": scope,
                            "lighting_scope": scope, "information_scope": scope}
                self.assertEqual(recent_context(previous, scope, now=101,
                                                idle_seconds=10), ((), None, None))

    def test_hostile_scope_subclass_is_rejected_without_comparison(self):
        class HostileText(str):
            def __eq__(self, other):
                raise RuntimeError("unexpected comparison")
        scope = ("assist", "device", HostileText("user"), None)
        previous = {**self.previous, "device_status_scope": scope}
        self.assertEqual(recent_context(previous, scope, now=101,
                                        idle_seconds=10), ((), None, None))

    def test_corrupt_stored_scopes_cannot_restore_context_or_raise(self):
        class HostileText(str):
            def __eq__(self, other):
                raise RuntimeError("stored scope must not be compared")
        for stored in (HostileText("kitchen"),
                       ("assist", "device", HostileText("user"), None),
                       ("assist", None, None, None)):
            with self.subTest(stored=repr(stored)):
                previous = {**self.previous, "device_status_scope": stored,
                            "lighting_scope": stored, "information_scope": stored}
                self.assertEqual(recent_context(previous, "kitchen", now=101,
                                                idle_seconds=10), ((), None, None))

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

    def test_invalid_clock_or_idle_interval_fails_closed(self):
        cases = ((float("nan"), 10), (float("inf"), 10), ("now", 10),
                 (True, 10), (101, float("nan")), (101, float("inf")),
                 (101, -1), (101, 0), (101, "ten"), (101, True))
        for now, idle_seconds in cases:
            with self.subTest(now=repr(now), idle_seconds=repr(idle_seconds)):
                self.assertEqual(recent_context(self.previous, "kitchen", now=now,
                                                idle_seconds=idle_seconds),
                                 ((), None, None))

    def test_extremely_large_integer_metadata_fails_closed(self):
        huge = 10 ** 1000
        for previous, now, idle_seconds in (
            (self.previous, huge, 10),
            (self.previous, 101, huge),
            ({**self.previous, "at": huge}, 101, 10),
        ):
            with self.subTest(now=now, idle_seconds=idle_seconds):
                self.assertEqual(recent_context(previous, "kitchen", now=now,
                                                idle_seconds=idle_seconds),
                                 ((), None, None))

    def test_assist_tuple_scope_retains_valid_context(self):
        scope = ("assist", "device-1", None, "assist_satellite.kitchen")
        previous = {**self.previous, "device_status_scope": scope,
                    "lighting_scope": scope, "information_scope": scope}
        self.assertEqual(recent_context(previous, scope, now=101, idle_seconds=10),
                         (("light.kitchen",), "light.kitchen", ("weather",)))

    def test_non_mapping_previous_context_is_ignored(self):
        for previous in ("hello", [], 123):
            with self.subTest(previous=repr(previous)):
                self.assertEqual(recent_context(previous, "kitchen", now=101, idle_seconds=10),
                                 ((), None, None))

    def test_missing_context_values_use_defaults(self):
        self.assertEqual(recent_context({"at": 100, "lighting_scope": "kitchen"},
                                        "kitchen", now=101, idle_seconds=10),
                         ((), None, None))
