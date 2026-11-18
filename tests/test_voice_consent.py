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

    def test_consent_events_are_bounded_and_have_no_audio_or_identity_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(voice_profiles, 'DATABASE', Path(temp) / 'voice.sqlite3'):
                profile = voice_profiles.manage({
                    'operation': 'create', 'name': 'Test Person', 'consent': True
                })['profiles'][0]['id']
                for _ in range(12):
                    voice_profiles.manage({
                        'operation': 'revoke_consent', 'profile': profile, 'confirm': True
                    })
                    voice_profiles.manage({
                        'operation': 'grant_consent', 'profile': profile, 'consent': True
                    })
                listing = voice_profiles.listing()['profiles'][0]
                self.assertEqual(len(listing['consent_events']), 20)
                self.assertEqual(listing['consent_events'][0]['action'], 'granted')
                self.assertEqual(listing['consent_events'][1]['action'], 'revoked')
                self.assertTrue(all(set(event) == {'action', 'recorded_at'}
                                    for event in listing['consent_events']))
                self.assertTrue(all(isinstance(event['recorded_at'], float)
                                    for event in listing['consent_events']))
                self.assertNotIn('audio', str(listing['consent_events']))
                self.assertNotIn('digest', str(listing['consent_events']))

    def test_profile_deletion_purges_consent_audit_identifiers_and_samples(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(voice_profiles, 'DATABASE', Path(temp) / 'voice.sqlite3'):
                profile = voice_profiles.manage({
                    'operation': 'create', 'name': 'Test Person', 'consent': True
                })['profiles'][0]['id']
                with patch.object(voice_profiles, 'validate_audio',
                                  return_value=(b'test-audio', 1.0)):
                    voice_profiles.manage({
                        'operation': 'save_sample', 'profile': profile,
                        'consent': True, 'audio': 'test'
                    })
                with self.assertRaises(ValueError):
                    voice_profiles.manage({'operation': 'delete_profile', 'profile': profile})
                voice_profiles.manage({
                    'operation': 'delete_profile', 'profile': profile, 'confirm': True
                })
                self.assertEqual(voice_profiles.listing()['profiles'], [])
                with voice_profiles.database() as db:
                    self.assertEqual(db.execute(
                        'SELECT count(*) FROM consent_events WHERE profile = ?',
                        (profile,)).fetchone()[0], 0)
                    self.assertEqual(db.execute(
                        'SELECT count(*) FROM samples WHERE profile = ?',
                        (profile,)).fetchone()[0], 0)

    def test_revocation_requires_explicit_confirmation(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(voice_profiles, 'DATABASE', Path(temp) / 'voice.sqlite3'):
                profile = voice_profiles.manage({'operation': 'create', 'name': 'Test Person', 'consent': True})['profiles'][0]['id']
                with self.assertRaises(ValueError):
                    voice_profiles.manage({'operation': 'revoke_consent', 'profile': profile})
                self.assertIsNotNone(voice_profiles.listing()['profiles'][0]['consent_at'])


if __name__ == '__main__':
    unittest.main()
