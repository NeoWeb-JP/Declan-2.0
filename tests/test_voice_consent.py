"""Regression coverage for local voice consent state and revocation."""
import tempfile
import os
import base64
import unittest
from pathlib import Path
from unittest.mock import patch

import voice_profiles


@patch.dict(os.environ, {'DECLAN_VOICE_AUDIO_KEY': base64.urlsafe_b64encode(b'k' * 32).decode()})
class LocalVoiceConsentTests(unittest.TestCase):
    def test_revoke_removes_samples_and_requires_new_consent(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(voice_profiles, 'DATABASE', Path(temp) / 'voice.sqlite3'):
                created = voice_profiles.manage({'operation': 'create', 'name': 'Test Person', 'consent': True})
                profile = created['profiles'][0]['id']
                with patch.object(voice_profiles, 'validate_audio', return_value=(b'valid-test-audio', 1.0)):
                    voice_profiles.manage({'operation': 'save_sample', 'profile': profile, 'consent': True, 'audio': 'test'})
                    revoked = voice_profiles.manage({'operation': 'revoke_consent', 'profile': profile, 'confirm': True})
                    self.assertIsNone(revoked['profiles'][0]['consent_at'])
                    self.assertEqual(revoked['profiles'][0]['samples'], [])
                    with self.assertRaisesRegex(ValueError, 'revoked'):
                        voice_profiles.manage({'operation': 'save_sample', 'profile': profile, 'consent': True, 'audio': 'test'})
                    voice_profiles.manage({'operation': 'grant_consent', 'profile': profile, 'consent': True})
                    voice_profiles.manage({'operation': 'save_sample', 'profile': profile, 'consent': True, 'audio': 'test'})
                with voice_profiles.database() as db:
                    events = list(db.execute('SELECT action FROM consent_events WHERE profile = ? ORDER BY id', (profile,)))
                self.assertEqual(events, [('granted',), ('revoked',), ('granted',)])

    def test_revocation_requires_explicit_confirmation(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(voice_profiles, 'DATABASE', Path(temp) / 'voice.sqlite3'):
                profile = voice_profiles.manage({'operation': 'create', 'name': 'Test Person', 'consent': True})['profiles'][0]['id']
                with self.assertRaises(ValueError):
                    voice_profiles.manage({'operation': 'revoke_consent', 'profile': profile})
                self.assertIsNotNone(voice_profiles.listing()['profiles'][0]['consent_at'])


if __name__ == '__main__':
    unittest.main()
