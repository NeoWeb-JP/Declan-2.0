"""One-shot retry context and scope isolation tests."""
import unittest
from retry_context import consume_pending_retry


class RetryContextTests(unittest.TestCase):
    def setUp(self):
        self.retry = {"text": "turn off lights", "scope": "kitchen", "at": 100}
        self.session = {"pending_retry": self.retry}

    def consume(self, scope="kitchen", now=105):
        return consume_pending_retry(self.session, scope, now=now, window_seconds=10)

    def test_malformed_pending_retry_is_discarded_once(self):
        for pending in (None, "retry", 42, [], {"scope": "kitchen"},
                        {"scope": "kitchen", "at": "yesterday"},
                        {"scope": "kitchen", "at": True},
                        {"scope": "kitchen", "at": float("nan")},
                        {"scope": "kitchen", "at": float("inf")},
                        {"scope": "kitchen", "at": 106}):
            with self.subTest(pending=repr(pending)):
                self.session["pending_retry"] = pending
                self.assertIsNone(self.consume())
                self.assertNotIn("pending_retry", self.session)

    def test_malformed_session_is_ignored(self):
        for session in ("text", [], 42):
            with self.subTest(session=repr(session)):
                self.assertIsNone(consume_pending_retry(session, "kitchen", now=105, window_seconds=10))

    def test_invalid_clock_window_or_scope_discards_pending_once(self):
        cases = ((float("nan"), 10, "kitchen"), (float("inf"), 10, "kitchen"),
                 (105, float("nan"), "kitchen"), (105, float("inf"), "kitchen"),
                 (105, -1, "kitchen"), (105, "ten", "kitchen"),
                 (105, True, "kitchen"), (105, 10, None), (105, 10, ""),
                 (105, 10, []), (105, 10, 42))
        for now, window, scope in cases:
            with self.subTest(now=repr(now), window=repr(window), scope=repr(scope)):
                session = {"pending_retry": dict(self.retry)}
                self.assertIsNone(consume_pending_retry(session, scope, now=now,
                                                        window_seconds=window))
                self.assertNotIn("pending_retry", session)

    def test_assist_tuple_scope_preserves_retry_and_cancellation(self):
        scope = ("assist", "kitchen", None, None)
        pending = {"text": "office light on it", "scope": scope, "at": 100}
        session = {"pending_retry": pending}
        self.assertIs(consume_pending_retry(session, scope, now=105,
                                            window_seconds=30), pending)
        self.assertNotIn("pending_retry", session)

    def test_oversized_integer_retry_metadata_is_consumed_safely(self):
        huge = 10 ** 1000
        for now, window, at in ((huge, 30, 100), (105, huge, 100),
                                (105, 30, huge)):
            with self.subTest(oversized=(now == huge, window == huge, at == huge)):
                session = {"pending_retry": {**self.retry, "at": at}}
                self.assertIsNone(consume_pending_retry(session, "kitchen", now=now,
                                                        window_seconds=window))
                self.assertNotIn("pending_retry", session)

    def test_matching_retry_is_returned(self):
        self.assertIs(self.consume(), self.retry)

    def test_retry_is_consumed_once(self):
        self.assertIs(self.consume(), self.retry)
        self.assertIsNone(self.consume())

    def test_expired_retry_is_dropped(self):
        self.assertIsNone(self.consume(now=111))
        self.assertNotIn("pending_retry", self.session)

    def test_exact_timeout_boundary_is_valid(self):
        self.assertIs(self.consume(now=110), self.retry)

    def test_other_room_retry_is_dropped(self):
        self.assertIsNone(self.consume(scope="bedroom"))

    def test_unknown_scope_drops_retry(self):
        self.assertIsNone(self.consume(scope=None))

    def test_no_session_returns_none(self):
        self.assertIsNone(consume_pending_retry(None, "kitchen", now=105, window_seconds=10))

    def test_session_without_retry_returns_none(self):
        self.assertIsNone(consume_pending_retry({}, "kitchen", now=105, window_seconds=10))
