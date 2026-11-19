"""Default command vocabulary stays compatible with server public symbols."""
import re
import unittest

from declan.turn import command_vocabulary as vocabulary
import server


class CommandVocabularyTests(unittest.TestCase):
    def test_server_exports_same_mutable_objects(self):
        for name in (
            "SEXY_TIME_COMMANDS", "DINNER_PHRASES", "GUEST_COMMANDS",
            "CHAT_COMMANDS", "GOOD_MORNING_PHRASES", "GOOD_NIGHT_PHRASES",
            "NAME_PATTERN",
        ):
            with self.subTest(name=name):
                self.assertIs(getattr(server, name), getattr(vocabulary, name))

    def test_sexy_time_variants_and_end_commands(self):
        self.assertEqual(server.SEXY_TIME_COMMANDS["sixty time"], "start")
        self.assertEqual(server.SEXY_TIME_COMMANDS["start bedroom mood"], "start")
        self.assertEqual(server.SEXY_TIME_COMMANDS["stop bedroom mood"], "end")

    def test_guest_and_conversation_intents(self):
        self.assertEqual(server.GUEST_COMMANDS["guests have left"], "clear")
        self.assertEqual(server.GUEST_COMMANDS["who is in charge"], "check")
        self.assertEqual(server.CHAT_COMMANDS["what time is it"], "time")
        self.assertIsInstance(server.NAME_PATTERN, re.Pattern)
        self.assertIsNotNone(server.NAME_PATTERN.search("my name is Jaco"))

    def test_routine_phrase_defaults(self):
        self.assertIn("good morning", server.GOOD_MORNING_PHRASES)
        self.assertIn("goodnight", server.GOOD_NIGHT_PHRASES)
        self.assertIn("dinner time", server.DINNER_PHRASES)


if __name__ == "__main__":
    unittest.main()
