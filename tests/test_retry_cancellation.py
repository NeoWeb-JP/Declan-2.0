"""Retry cancellation response and persistence regression tests."""
import sqlite3
import unittest
from unittest.mock import Mock
from declan.turn.retry_cancellation import cancel_retry


class RetryCancellationTests(unittest.TestCase):
    def setUp(self):
        self.converse = Mock(return_value={"session_id": "new-session", "reply": ""})
        self.record = Mock()
        self.log_error = Mock()

    def cancel(self, source="assist", speaker="Jaco"):
        return cancel_retry("cancel", "old-session", scope="kitchen",
            source=source, speaker=speaker, converse=self.converse,
            record=self.record, log_error=self.log_error)

    def test_response_is_cancelled_and_stops_listening(self):
        reply = self.cancel()
        self.assertEqual(reply["outcome"], "cancelled")
        self.assertFalse(reply["continue_conversation"])

    def test_converse_receives_scope_and_empty_response(self):
        self.cancel()
        self.converse.assert_called_once_with(
            "cancel", "old-session", "", scope="kitchen")

    def test_assist_history_keeps_speaker(self):
        self.cancel()
        self.record.assert_called_once_with(
            "new-session", "assist", "cancel", "", "cancelled", speaker="Jaco")

    def test_browser_history_does_not_keep_speaker(self):
        self.cancel(source="browser_voice")
        self.assertIsNone(self.record.call_args.kwargs["speaker"])

    def test_sqlite_failure_is_nonfatal(self):
        self.record.side_effect = sqlite3.Error("database unavailable")
        self.assertFalse(self.cancel()["history_saved"])
        self.log_error.assert_called_once()

    def test_os_failure_is_nonfatal(self):
        self.record.side_effect = OSError("disk full")
        self.assertFalse(self.cancel()["history_saved"])

    def test_success_does_not_set_history_failure(self):
        self.assertNotIn("history_saved", self.cancel())
