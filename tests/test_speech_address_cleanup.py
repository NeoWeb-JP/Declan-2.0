"""Speech-to-text keeps how people address Declan; matching must not care."""
import unittest

from declan.core.history import normalize_phrase
from declan.turn import conversation_turn
from declan.turn.command_vocabulary import CHAT_COMMANDS, GOOD_NIGHT_PHRASES
from declan.turn.intent_preprocessing import preprocess_speech


def spoken(raw):
    return normalize_phrase(preprocess_speech(raw).commands[0])


class AddressCleanupTests(unittest.TestCase):
    def test_address_and_courtesy_words_are_dropped(self):
        cases = {
            "Declan, turn on the kitchen lights.": "turn on the kitchen lights",
            "Hey, turn on the kitchen lights please": "turn on the kitchen lights",
            "Okay Declan, play some jazz": "play some jazz",
            "Howzit Declan, pause the music": "pause the music",
            "Pause the music, please.": "pause the music",
            "Turn off the lounge lights, thanks.": "turn off the lounge lights",
            "What's the time, Declan?": "what's the time",
            "Hey, what time is it?": "what time is it",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(spoken(raw), expected)

    def test_good_night_with_address_reaches_the_routine(self):
        self.assertIn(spoken("Good night, Declan."), GOOD_NIGHT_PHRASES)

    def test_short_phrases_and_command_style_words_are_kept(self):
        self.assertEqual(spoken("Hello Declan"), "hello declan")
        self.assertEqual(spoken("Yes please"), "yes please")
        self.assertEqual(spoken("Declan"), "declan")
        self.assertEqual(spoken("Turn on the office light my bru"), "turn on the office light my bru")

    def test_device_words_that_look_like_greetings_are_untouched(self):
        self.assertEqual(spoken("hey there"), "hey there")
        self.assertEqual(spoken("okay turn it off"), "okay turn it off")


class TimeQuestionTests(unittest.TestCase):
    def test_everyday_ways_of_asking_the_time(self):
        for raw in ("What was the time?", "What's the time now?", "What’s the time now?",
                    "Can you tell me the time?", "Do you know what time it is?",
                    "Declan, what's the time please?", "What time is it right now?"):
            with self.subTest(raw=raw):
                self.assertEqual(CHAT_COMMANDS.get(spoken(raw)), "time")


class ConversationOffTests(unittest.TestCase):
    def test_general_questions_need_conversation(self):
        self.assertTrue(conversation_turn.needs_conversation("Where is South Africa?", CHAT_COMMANDS))
        self.assertTrue(conversation_turn.needs_conversation("Who wrote Hamlet", CHAT_COMMANDS))

    def test_local_questions_and_commands_do_not(self):
        for message in ("what was the time", "what's my name", "turn on the kitchen lights",
                        "is the kitchen light on", "what can you do"):
            with self.subTest(message=message):
                self.assertFalse(conversation_turn.needs_conversation(message, CHAT_COMMANDS))

    def test_time_questions_are_built_in_chat_commands(self):
        for message in ("What was the time?", "what time was it", "What's the time"):
            with self.subTest(message=message):
                self.assertTrue(conversation_turn.is_chat_command(message, CHAT_COMMANDS))
        self.assertFalse(conversation_turn.is_chat_command("where is south africa", CHAT_COMMANDS))

    def test_reply_says_how_to_switch_it_on(self):
        self.assertIn("Let Declan understand everyday speech", conversation_turn.CONVERSATION_OFF_REPLY)


if __name__ == "__main__":
    unittest.main()
