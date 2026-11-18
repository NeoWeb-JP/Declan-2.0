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
