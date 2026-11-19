"""Retry transcript contract regression tests."""
import unittest

from retry_phrase_validation import MAX_RETRY_PHRASE_LENGTH, valid_retry_phrase


class RetryPhraseValidationTests(unittest.TestCase):
    def test_valid_voice_phrases(self):
        for value in ("turn on the office light", "  kitchen lights off  ",
                      "x" * MAX_RETRY_PHRASE_LENGTH):
            with self.subTest(length=len(value)):
                self.assertTrue(valid_retry_phrase(value))

    def test_invalid_voice_phrases(self):
        class HostileText(str):
            def strip(self, chars: str | None = None) -> str:
                raise RuntimeError("unexpected subclass operation")

        value: object
        for value in (None, 42, [], {}, "", "  ", True,
                      "x" * (MAX_RETRY_PHRASE_LENGTH + 1), HostileText("lights on")):
            with self.subTest(type=type(value).__name__):
                self.assertFalse(valid_retry_phrase(value))


if __name__ == "__main__":
    unittest.main()
