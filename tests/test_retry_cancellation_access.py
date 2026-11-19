"""Retry cancellation lock and argument forwarding regressions."""

import threading
import unittest
from unittest.mock import Mock

from declan.turn.retry_cancellation_access import cancel_pending_retry


class RetryCancellationAccessTests(unittest.TestCase):
    def test_cancel_forwards_context_and_returns_result(self):
        lock = threading.RLock()
        converse = Mock()
        record = Mock()
        log_error = Mock()
        cancel = Mock(return_value="cancelled")
        result = cancel_pending_retry(
            message="stop", session_id="session-1", scope="kitchen",
            source="assist", speaker="edd", lock=lock,
            converse=converse, record=record, log_error=log_error,
            cancel=cancel,
        )
        self.assertEqual(result, "cancelled")
        cancel.assert_called_once_with(
            "stop", "session-1", scope="kitchen", source="assist",
            speaker="edd", converse=converse, record=record,
            log_error=log_error,
        )

    def test_cancel_runs_under_lock(self):
        lock = threading.Lock()
        def cancel(*args, **kwargs):
            self.assertFalse(lock.acquire(blocking=False))
            return "cancelled"
        self.assertEqual(cancel_pending_retry(
            message="cancel", session_id="s", scope="room", source="chat",
            speaker=None, lock=lock, converse=None, record=None,
            log_error=None, cancel=cancel,
        ), "cancelled")


if __name__ == "__main__":
    unittest.main()
