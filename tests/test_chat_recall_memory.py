"""Short-term chat recall must not revive timed-out action context."""

from collections import OrderedDict
import re
import unittest
from unittest.mock import patch

from chat_recall_memory import ChatRecallMemory, RECALL_SECONDS
import session_orchestration


class ChatRecallTests(unittest.TestCase):
    def setUp(self):
        self.clock = [1000.0]
        self.sessions = OrderedDict()
        self.recall = ChatRecallMemory()
        self.commands = {
            "what's my name": "recall_name",
            "what did i say earlier": "recall_earlier",
            "forget this conversation": "forget_chat",
        }
        self.kwargs = {
            "sessions": self.sessions, "idle_seconds": 300,
            "name_pattern": re.compile(r"my name is ([a-z]+)", re.I),
            "chat_commands": self.commands, "unmatched_reply": "Unknown",
            "decorate": lambda line, category, mode: line,
            "recall": self.recall,
        }

    def say(self, message, sid=None, **extra):
        with patch.object(session_orchestration, "monotonic", return_value=self.clock[0]):
            return session_orchestration.converse(message, sid, **self.kwargs, **extra)

    def test_chat_recall_survives_action_expiry_without_reviving_actions(self):
        first = self.say("my name is Alex", lighting_context=("light.office",), scope="study")
        sid = first["session_id"]
        self.clock[0] += 301
        recalled = self.say("what's my name", sid)
        self.assertEqual(recalled["session_id"], sid)
        self.assertEqual(recalled["reply"], "Your name is Alex.")
        self.assertNotIn("lighting_context", self.sessions[sid])
        self.assertNotIn("lighting_scope", self.sessions[sid])

    def test_last_three_messages_are_bounded_and_session_isolated(self):
        first = self.say("hello")
        sid = first["session_id"]
        for msg in ("one", "two", "three", "four"):
            self.say(msg, sid)
        result = self.say("what did i say earlier", sid)
        self.assertEqual(result["reply"], "Earlier you said: two | three | four")
        other = self.say("what did i say earlier")
        self.assertEqual(other["reply"], "I don't have earlier messages to recall.")

    def test_recall_expires_after_thirty_minutes_without_activity(self):
        first = self.say("my name is Alex")
        sid = first["session_id"]
        self.clock[0] += RECALL_SECONDS
        result = self.say("what's my name", sid)
        self.assertNotEqual(result["session_id"], sid)
        self.assertEqual(result["reply"], "I don't know your name yet.")
        self.assertNotIn(sid, self.recall.entries)

    def test_forget_clears_name_messages_and_action_context(self):
        first = self.say("my name is Alex", lighting_context=("light.office",), scope="study")
        sid = first["session_id"]
        self.assertIn(sid, self.recall.entries)
        forgotten = self.say("forget this conversation", sid,
                             lighting_context=("light.other",), scope="study")
        self.assertIn("cleared", forgotten["reply"])
        self.assertNotIn(sid, self.recall.entries)
        self.assertIsNone(self.sessions[sid]["name"])
        self.assertIsNone(self.sessions[sid]["last"])
        self.assertNotIn("lighting_context", self.sessions[sid])
        self.assertEqual(self.say("what's my name", sid)["reply"],
                         "I don't know your name yet.")

    def test_storage_bounds_and_raw_data_are_not_persisted(self):
        recall = ChatRecallMemory()
        for n in range(140):
            recall.remember(f"session-{n}", {
                "name": "A" * 100,
                "last": "x" * 1000,
                "recent_messages": ["y" * 400] * 8,
                "lighting_context": ("light.private",),
                "speaker": "private-speaker",
                "token": "private-token",
            }, 200.0)
        self.assertEqual(len(recall.entries), 128)
        payload = str(recall.entries)
        self.assertNotIn("private-token", payload)
        self.assertNotIn("private-speaker", payload)
        self.assertNotIn("light.private", payload)
        restored = recall.restore("session-139", 201.0)
        self.assertEqual(len(restored["name"]), 40)
        self.assertEqual(len(restored["last"]), 160)
        self.assertEqual(len(restored["recent_messages"]), 3)
        self.assertTrue(all(len(x) == 160 for x in restored["recent_messages"]))

    def test_memory_only_survives_in_same_process_store(self):
        first = self.say("my name is Alex")
        session_id = first["session_id"]
        fresh = ChatRecallMemory()
        self.assertIsNone(fresh.restore(session_id, self.clock[0] + 301))


if __name__ == "__main__":
    unittest.main()
