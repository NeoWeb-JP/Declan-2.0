"""Verify legacy sensitive routine and trusted speaker environment boundaries."""
import os
import unittest
from unittest.mock import patch

import sensitive_confirmations as confirmations


class SensitiveEnvironmentBoundariesTests(unittest.TestCase):
    def test_default_groups_and_explicit_empty_override(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(confirmations.groups(), {"night", "guest"})
        with patch.dict(os.environ, {"DECLAN_SENSITIVE_ROUTINES": ""}, clear=True):
            self.assertEqual(confirmations.groups(), set())

    def test_group_names_are_trimmed_normalized_and_deduplicated(self):
        with patch.dict(os.environ, {
                "DECLAN_SENSITIVE_ROUTINES": " Night, GUEST, night, , Movie "} , clear=True):
            self.assertEqual(confirmations.groups(), {"night", "guest", "movie"})

    def test_trusted_speakers_default_to_none(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(confirmations.trusted_speaker({"name": "Jaco", "confidence": 1.0}))

    def test_trusted_speaker_requires_exact_normalized_name(self):
        with patch.dict(os.environ, {"DECLAN_TRUSTED_SPEAKERS": " Edd, JACO "}, clear=True):
            self.assertTrue(confirmations.trusted_speaker({"name": " jaco ", "confidence": 0.85}))
            self.assertTrue(confirmations.trusted_speaker({"name": "EDD", "confidence": 1.0}))
            self.assertFalse(confirmations.trusted_speaker({"name": "Unknown", "confidence": 1.0}))

    def test_trusted_speaker_rejects_invalid_confidence_and_identity(self):
        with patch.dict(os.environ, {"DECLAN_TRUSTED_SPEAKERS": "Jaco"}, clear=True):
            for confidence in (None, True, "0.99", -1, 0.849, 1.01):
                with self.subTest(confidence=confidence):
                    self.assertFalse(confirmations.trusted_speaker({
                        "name": "Jaco", "confidence": confidence}))
            for speaker in (None, "Jaco", {}, {"name": "", "confidence": 1.0}):
                with self.subTest(speaker=speaker):
                    self.assertFalse(confirmations.trusted_speaker(speaker))


if __name__ == "__main__":
    unittest.main()
