"""Conversation persistence regression tests."""
import sqlite3
import unittest
from unittest.mock import Mock
from conversation_persistence import save_turn


class ConversationPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.record = Mock()
        self.log = Mock()
        self.diagnostic = Mock(return_value="trace-123")

    def save(self, *, source="assist", speaker="Jaco", actions=None):
        reply = {"session_id": "session-1", "reply": "Sorted."}
        actions = [] if actions is None else actions
        success = save_turn(reply, source=source, message="good morning",
            outcome="reported_success", routine_status={"status": "completed"},
            action_results=actions, phrase_suggestion=None, speaker=speaker,
            record=self.record, diagnostic_id=self.diagnostic, log_error=self.log)
        return reply, success

    def test_assist_records_speaker_and_diagnostics(self):
        reply, success = self.save()
        self.assertTrue(success)
        self.assertEqual(self.record.call_args.kwargs["speaker"], "Jaco")
        self.assertEqual(self.record.call_args.kwargs["diagnostic_id"], "trace-123")
        self.assertNotIn("history_saved", reply)

    def test_non_assist_does_not_record_speaker(self):
        _, success = self.save(source="chat")
        self.assertTrue(success)
        self.assertIsNone(self.record.call_args.kwargs["speaker"])

    def test_action_results_included_after_success(self):
        actions = [{"target": "light.kitchen", "status": "confirmed"}]
        reply, success = self.save(actions=actions)
        self.assertTrue(success)
        self.assertEqual(reply["action_results"], actions)

    def test_no_action_results_key_when_empty(self):
        reply, _ = self.save()
        self.assertNotIn("action_results", reply)

    def test_sqlite_failure_sets_history_flag(self):
        self.record.side_effect = sqlite3.OperationalError("database locked")
        reply, success = self.save(actions=[{"target": "light.kitchen"}])
        self.assertFalse(success)
        self.assertFalse(reply["history_saved"])
        self.assertNotIn("action_results", reply)
        self.log.assert_called_once_with("Could not save conversation history.")

    def test_os_failure_sets_history_flag(self):
        self.record.side_effect = OSError("disk full")
        reply, success = self.save()
        self.assertFalse(success)
        self.assertFalse(reply["history_saved"])
