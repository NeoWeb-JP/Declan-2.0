"""Verify legacy confirmation settings remain explicit and fail closed."""
import os
import unittest
from unittest.mock import patch

from sensitive_confirmations import groups, trusted_speaker


class SensitiveConfirmationEnvironmentTests(unittest.TestCase):
    def test_unset_groups_default_to_night_and_guest(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(groups(), {"night", "guest"})

    def test_empty_and_normalized_group_overrides(self):
        with patch.dict(os.environ, {"DECLAN_SENSITIVE_ROUTINES": ""}):
            self.assertEqual(groups(), set())
        with patch.dict(os.environ, {"DECLAN_SENSITIVE_ROUTINES": " Night , GUEST, movie, "}):
            self.assertEqual(groups(), {"night", "guest", "movie"})

    def test_unset_trusted_speakers_does_not_trust_anyone(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(trusted_speaker({"name": "Jaco", "confidence": 1.0}))

    def test_explicit_speaker_allowlist_requires_high_confidence(self):
        with patch.dict(os.environ, {"DECLAN_TRUSTED_SPEAKERS": " Jaco, Edd "}):
            self.assertTrue(trusted_speaker({"name": "jaco", "confidence": 0.85}))
            self.assertTrue(trusted_speaker({"name": "EDD", "confidence": 1.0}))
            self.assertFalse(trusted_speaker({"name": "Other", "confidence": 1.0}))
            self.assertFalse(trusted_speaker({"name": "Jaco", "confidence": 0.84}))
            self.assertFalse(trusted_speaker({"name": "Jaco", "confidence": True}))
            self.assertFalse(trusted_speaker(None))


if __name__ == "__main__":
    unittest.main()
