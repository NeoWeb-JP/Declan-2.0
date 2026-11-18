"""Short-term chat recall must not revive timed-out action context."""

from collections import OrderedDict
import re
import unittest
from unittest.mock import patch

from chat_recall_memory import ChatRecallMemory, RECALL_SECONDS
from chat_recall_privacy import safe_chat_text
import session_orchestration


class ChatRecallTests(unittest.TestCase):
    def setUp(self):
        self.clock = [1000.0]
        self.sessions = OrderedDict()
        self.recall = ChatRecallMemory()
        self.commands = {
            "what's my name": "recall_name",
            "what did i say earlier": "recall_earlier",
            "what did i just say": "recall_message",
            "forget this conversation": "forget_chat",
            "hello declan": "greeting",
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

    def test_non_string_messages_fail_before_mutating_sessions(self):
        self.say("hello")
        before = list(self.sessions.items())
        for bad in (None, 123, [], {}):
            with self.subTest(bad=repr(bad)):
                with self.assertRaisesRegex(ValueError, "chat message must be a string"):
                    self.say(bad)
                self.assertEqual(list(self.sessions.items()), before)

    def test_corrupt_active_sessions_are_pruned_without_crashing(self):
        self.sessions["missing-at"] = {"name": "Alex"}
        self.sessions["not-a-dict"] = None
        self.sessions["bad-at"] = {"at": "yesterday"}
        self.say("hello")
        for key in ("missing-at", "not-a-dict", "bad-at"):
            self.assertNotIn(key, self.sessions)

    def test_invalid_client_session_ids_get_fresh_opaque_ids(self):
        for bad in ([], {}, 123, True, "", "x" * 257):
            with self.subTest(bad=repr(bad)):
                result = self.say("hello", bad)
                self.assertIsInstance(result["session_id"], str)
                self.assertNotEqual(result["session_id"], bad)
                self.assertIn(result["session_id"], self.sessions)

    def test_unknown_string_session_id_is_not_adopted(self):
        result = self.say("hello", "attacker-chosen-session")
        self.assertNotEqual(result["session_id"], "attacker-chosen-session")
        self.assertNotIn("attacker-chosen-session", self.sessions)

    def test_routine_reply_keeps_action_context_when_forget_phrase_overridden(self):
        first = self.say("my name is Alex")
        sid = first["session_id"]
        result = self.say("forget this conversation", sid, routine_reply="Done",
                          lighting_context=("light.study",), scope="study")
        self.assertEqual(result["reply"], "Done")
        self.assertEqual(self.sessions[sid]["lighting_context"], ("light.study",))
        self.assertEqual(self.sessions[sid]["lighting_scope"], "study")
        self.assertEqual(self.recall.entries[sid]["name"], "Alex")

    def test_forget_command_cannot_restore_expired_action_context(self):
        first = self.say("hello", lighting_context=("light.study",), scope="study")
        sid = first["session_id"]
        self.clock[0] += 301
        self.say("forget this conversation", sid)
        self.assertNotIn("lighting_context", self.sessions[sid])
        self.assertNotIn(sid, self.recall.entries)

    def test_routine_reply_takes_precedence_over_chat_commands(self):
        first = self.say("my name is Alex")
        sid = first["session_id"]
        result = self.say("forget this conversation", sid, routine_reply="Routine complete")
        self.assertEqual(result["reply"], "Routine complete")
        self.assertIn(sid, self.recall.entries)
        self.assertEqual(self.say("what\'s my name", sid)["reply"], "Your name is Alex.")

    def test_forget_reply_clears_recall_without_leaking_old_name(self):
        first = self.say("my name is Alex")
        sid = first["session_id"]
        result = self.say("forget this conversation", sid)
        self.assertIn("cleared", result["reply"])
        self.assertNotIn(sid, self.recall.entries)
        self.assertIsNone(self.sessions[sid]["name"])

    def test_greeting_never_speaks_unsafe_legacy_session_name(self):
        first = self.say("hello")
        sid = first["session_id"]
        self.sessions[sid]["name"] = "my password is synthetic-test-value"
        result = self.say("hello declan", sid)
        self.assertEqual(result["reply"], "Hello. I\'m Declan.")
        self.assertIsNone(self.sessions[sid]["name"])

    def test_safe_history_is_revalidated_before_adding_new_turn(self):
        first = self.say("hello")
        sid = first["session_id"]
        self.sessions[sid]["recent_messages"] = ["my password is synthetic-test-value", "hi"]
        self.say("the weather is lovely", sid)
        self.assertEqual(self.sessions[sid]["recent_messages"], ["hi", "the weather is lovely"])

    def test_expiry_prunes_all_sessions_even_if_order_is_not_chronological(self):
        self.sessions["fresh"] = {"at": 999.0}
        self.sessions["stale"] = {"at": 600.0}
        self.say("hello")
        self.assertIn("fresh", self.sessions)
        self.assertNotIn("stale", self.sessions)

    def test_session_store_evicts_oldest_access_and_keeps_128_entries(self):
        for n in range(128):
            self.sessions[f"session-{n}"] = {"at": self.clock[0], "last": None,
                                             "name": None, "recent_messages": []}
        self.say("hello", "session-0")
        self.say("hello")
        self.assertEqual(len(self.sessions), 128)
        self.assertIn("session-0", self.sessions)
        self.assertNotIn("session-1", self.sessions)

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
                "name": "Z" * 100,
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

    def test_sensitive_and_action_utterances_are_not_retained_or_replayed(self):
        first = self.say("my name is Alex")
        sid = first["session_id"]
        self.say("The password is secret-staging-value", sid)
        self.say("turn off the kitchen light", sid)
        self.say("please unlock the front door", sid)
        self.say("hello again", sid)
        self.clock[0] += 301
        result = self.say("what did i say earlier", sid)
        self.assertEqual(result["reply"], "Earlier you said: my name is Alex | hello again")
        self.assertEqual(self.recall.entries[sid]["last"], "what did i say earlier")
        stored = str(self.recall.entries[sid])
        self.assertNotIn("secret-staging-value", stored)
        self.assertNotIn("kitchen light", stored)
        self.assertNotIn("front door", stored)
        self.assertNotIn("password", stored)

    def test_a_routine_does_not_extend_or_populate_long_chat_recall(self):
        first = self.say("my name is Alex")
        sid = first["session_id"]
        self.clock[0] += 299
        self.say("sensitive household routine", sid, routine_reply="Done",
                 lighting_context=("light.private",), scope="study")
        self.assertNotIn("sensitive household routine", str(self.recall.entries[sid]))
        self.clock[0] += 1502
        self.assertIsNone(self.recall.restore(sid, self.clock[0]))
        self.assertNotIn("light.private", str(self.recall.entries))

    def test_direct_memory_cannot_store_secret_or_action_content(self):
        self.recall.remember("s", {"name": "Alex",
                                  "last": "my API key is sk-abcdefghijklmnop",
                                  "recent_messages": [
                                      "hello", "set thermostat to 30 degrees",
                                      "my passcode is 123456",
                                      "a harmless note",
                                  ]}, 100)
        self.assertIsNone(self.recall.restore("s", 101))
        self.recall.remember("s", {"last": "a harmless note",
                                   "recent_messages": ["hello", "set thermostat to 30 degrees",
                                                       "my passcode is 123456", "a harmless note"]}, 102)
        record = self.recall.restore("s", 103)
        self.assertEqual(record["recent_messages"], ["hello", "a harmless note"])
        self.assertNotIn("passcode", str(record))
        self.assertNotIn("thermostat", str(record))

    def test_active_session_never_repeats_private_last_message(self):
        first = self.say("hello")
        sid = first["session_id"]
        self.say("my password is synthetic-test-value", sid)
        response = self.say("what did i just say", sid)
        self.assertNotIn("synthetic-test-value", response["reply"])
        self.assertIn("safe earlier message", response["reply"])

    def test_active_session_filters_private_recent_messages_at_read_time(self):
        first = self.say("hello")
        sid = first["session_id"]
        self.sessions[sid]["recent_messages"] = [
            "hello", "my password is synthetic-test-value", "the weather is lovely"]
        response = self.say("what did i say earlier", sid)
        self.assertIn("hello", response["reply"])
        self.assertIn("the weather is lovely", response["reply"])
        self.assertNotIn("synthetic-test-value", response["reply"])

    def test_sensitive_name_is_rejected_even_before_session_expiry(self):
        first = self.say("my name is Alex")
        sid = first["session_id"]
        rejected = self.say("my name is password", sid)
        self.assertIn("cannot remember", rejected["reply"])
        self.assertEqual(self.say("what\'s my name", sid)["reply"], "Your name is Alex.")
        fresh = self.say("my name is password")
        self.assertEqual(self.say("what\'s my name", fresh["session_id"])["reply"],
                         "I don\'t know your name yet.")

    def test_private_name_is_not_retained_for_later_spoken_recall(self):
        self.recall.remember("s", {"name": "my API key is sk-abcdefghijklmnop",
                                   "last": "hello", "recent_messages": ["hello"]}, 100)
        record = self.recall.restore("s", 101)
        self.assertIsNone(record["name"])
        self.assertEqual(record["last"], "hello")
        self.assertNotIn("sk-abcdefghijklmnop", str(record))

    def test_sensitive_turn_cannot_extend_existing_recall_lifetime(self):
        self.recall.remember("s", {"name": "Alex", "last": "hello",
                                   "recent_messages": ["hello"]}, 100)
        original = dict(self.recall.entries["s"])
        self.recall.remember("s", {"name": "Alex",
                                   "last": "my password is a test secret",
                                   "recent_messages": ["hello"]}, 100 + RECALL_SECONDS - 1)
        self.assertEqual(self.recall.entries["s"], original)
        self.assertIsNone(self.recall.restore("s", 100 + RECALL_SECONDS))

    def test_additional_household_action_phrases_are_not_recalled(self):
        for phrase in ("close the garage", "shut the gate", "open the blinds",
                       "dim the lights", "brighten the lamp",
                       "lower the thermostat", "increase the heating",
                       "adjust temperature", "play music", "pause the radio"):
            with self.subTest(phrase=phrase):
                self.assertIsNone(safe_chat_text(phrase))
        self.assertEqual(safe_chat_text("the weather is lovely"), "the weather is lovely")

    def test_memory_only_survives_in_same_process_store(self):
        first = self.say("my name is Alex")
        session_id = first["session_id"]
        fresh = ChatRecallMemory()
        self.assertIsNone(fresh.restore(session_id, self.clock[0] + 301))


if __name__ == "__main__":
    unittest.main()
