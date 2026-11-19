"""Regression tests for speaker labels stored in conversation history."""
import unittest

from declan.core.history import speaker_match


class SpeakerMatchTests(unittest.TestCase):
    def test_preserves_recognized_speaker_name(self):
        self.assertEqual(
            speaker_match({"name": "Ed", "confidence": 0.9}),
            {"name": "Ed", "confidence": 0.9},
        )

    def test_preserves_candidate_name_below_threshold(self):
        self.assertEqual(
            speaker_match({"name": "Ed", "confidence": 0.5}),
            {"name": "Unknown", "candidate": "Ed", "confidence": 0.5},
        )

    def test_rejects_unknown_identity(self):
        self.assertEqual(
            speaker_match({"name": "unknown", "confidence": 0.9}),
            {"name": "Unknown", "confidence": 0.9},
        )


if __name__ == "__main__":
    unittest.main()
