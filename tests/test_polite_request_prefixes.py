"""Polite request wrappers reach the local parsers as ordinary commands."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import server
from declan.music import music
from declan.turn.intent_preprocessing import strip_polite_request
from declan.turn.learned_intent_resolution import resolve


class StripPoliteRequestTests(unittest.TestCase):
    def test_wrappers_are_removed_and_the_command_is_untouched(self):
        cases = {
            "can you turn on the office light": "turn on the office light",
            "could you please play country music everywhere": "play country music everywhere",
            "would you turn off the kitchen lights": "turn off the kitchen lights",
            "will you start movie time": "start movie time",
            "please turn off the kitchen lights": "turn off the kitchen lights",
            "please could you turn on the office light": "turn on the office light",
            "turn on the office light please": "turn on the office light",
            "turn on the office light my bru": "turn on the office light",
            "turn on the lights for me, please": "turn on the lights",
            "can you, please, dim the lounge lights": "dim the lounge lights",
            "would you mind turning off the bedroom lights": "turn off the bedroom lights",
            "do you mind playing rock in the lounge": "play rock in the lounge",
        }
        for spoken, expected in cases.items():
            with self.subTest(spoken=spoken):
                self.assertEqual(strip_polite_request(spoken), expected)

    def test_plain_commands_questions_and_unknown_phrasing_are_unchanged(self):
        for phrase in ("turn on the office light", "what time is it", "who is home",
                       "can you", "please", "would you mind if i sleep",
                       "would you mind", "my bru", "turn on the kitchen and dining lights"):
            with self.subTest(phrase=phrase):
                self.assertEqual(strip_polite_request(phrase), phrase)

    def test_one_word_remainders_keep_exact_match_meaning(self):
        for phrase in ("yes please", "stop please", "can you stop", "confirm please", "no thanks"):
            with self.subTest(phrase=phrase):
                self.assertEqual(strip_polite_request(phrase), phrase)

    def test_unwrapped_commands_are_understood_by_the_local_parsers(self):
        self.assertIsNone(server.parse_light_command("can you turn on the office light"))
        self.assertEqual(server.parse_light_command(strip_polite_request("can you turn on the office light")),
                         ("office light", "on"))
        self.assertEqual(server.parse_light_command(strip_polite_request("turn on the office light my bru")),
                         ("office light", "on"))
        self.assertIsNone(music.parse("could you play country music everywhere"))
        self.assertEqual(music.parse(strip_polite_request("could you play country music everywhere"))[0],
                         "everywhere")


class ResolutionTests(unittest.TestCase):
    def run_resolution(self, message, learned=None):
        lookups = []

        def learned_intent(phrase):
            lookups.append(phrase)
            return (learned or {}).get(phrase)
        result = resolve(message, preprocess=lambda m: SimpleNamespace(commands=[m]),
                         normalize=server.history.normalize_phrase,
                         learned_intent=learned_intent, log_error=Mock())
        return result, lookups

    def test_local_phrase_is_unwrapped_but_the_spoken_message_is_kept(self):
        (effective, phrase), lookups = self.run_resolution("Can you turn on the office light?")
        self.assertEqual(effective, "Can you turn on the office light?")
        self.assertEqual(phrase, "turn on the office light")
        self.assertEqual(lookups, ["can you turn on the office light", "turn on the office light"])

    def test_learned_phrase_matches_as_spoken_first_then_unwrapped(self):
        (effective, phrase), lookups = self.run_resolution(
            "can you do the thing", {"can you do the thing": "turn on the lounge lights"})
        self.assertEqual(phrase, "turn on the lounge lights")
        self.assertEqual(lookups, ["can you do the thing"])
        (effective, phrase), lookups = self.run_resolution(
            "could you do the thing please", {"do the thing": "turn on the lounge lights"})
        self.assertEqual((effective, phrase), ("turn on the lounge lights", "turn on the lounge lights"))

    def test_plain_phrase_is_looked_up_once(self):
        (_, phrase), lookups = self.run_resolution("turn on the office light")
        self.assertEqual(lookups, ["turn on the office light"])


if __name__ == "__main__":
    unittest.main()
