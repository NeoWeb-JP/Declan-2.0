from typing import Any, cast
import unittest

from declan.turn.intent_preprocessing import preprocess_speech


class SpeechPreprocessingTests(unittest.TestCase):
    def test_known_phrase_unchanged(self):
        self.assertEqual(preprocess_speech("movie time").commands, ("movie time",))

    def test_correction_replaces_earlier_action(self):
        result = preprocess_speech("turn off the kitchen, no, I mean movie time")
        self.assertEqual(result.commands, ("movie time",))
        self.assertTrue(result.corrected)

    def test_latest_correction_wins(self):
        result = preprocess_speech("lights, I mean music, actually I meant movie time")
        self.assertEqual(result.commands, ("movie time",))

    def test_fillers(self):
        self.assertEqual(preprocess_speech("umm movie uh time").commands, ("movie time",))

    def test_do_not_split_ambiguous_conjunction(self):
        self.assertEqual(
            preprocess_speech("turn on the kitchen and dining lights").commands,
            ("turn on the kitchen and dining lights",),
        )

    def test_invalid_or_empty(self):
        for text in ("", "uh erm", "turn on, I mean"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                preprocess_speech(text)

    def test_non_string(self):
        with self.assertRaises(ValueError):
            cast(Any, preprocess_speech)(None)


if __name__ == "__main__":
    unittest.main()
