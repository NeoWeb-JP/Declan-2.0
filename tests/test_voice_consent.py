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

    def test_revocation_sanitizes_retained_backup_after_live_commit(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as temp:
            data_dir = Path(temp)
            database = data_dir / 'voice.sqlite3'
            with patch.object(voice_profiles, 'DATABASE', database):
                profile = voice_profiles.manage({
                    'operation': 'create', 'name': 'Test Person', 'consent': True
                })['profiles'][0]['id']
                with patch.object(voice_profiles, 'validate_audio',
                                  return_value=(b'audio-for-test', 1.0)):
                    voice_profiles.manage({
                        'operation': 'save_sample', 'profile': profile,
                        'consent': True, 'audio': 'test'
                    })
                backup = data_dir / 'upgrade-backups' / 'legacy-release'
                backup.mkdir(parents=True)
                with sqlite3.connect(backup / 'voice-profiles.sqlite3') as db:
                    db.execute('CREATE TABLE samples (id TEXT PRIMARY KEY, audio BLOB)')
                    db.execute('INSERT INTO samples VALUES (?, ?)',
                               ('legacy-test', b'RIFF_private_test_audio'))
                result = voice_profiles.manage({
                    'operation': 'revoke_consent', 'profile': profile, 'confirm': True
                })
                self.assertIs(result['backup_cleanup_required'], False)
                self.assertEqual(result['profiles'][0]['samples'], [])
                with sqlite3.connect(backup / 'voice-profiles.sqlite3') as db:
                    self.assertEqual(db.execute('SELECT count(*) FROM samples').fetchone()[0], 0)
                self.assertNotIn(b'RIFF_private_test_audio',
                                 (backup / 'voice-profiles.sqlite3').read_bytes())

    def test_deleted_sample_and_profile_trigger_backup_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(voice_profiles, 'DATABASE', Path(temp) / 'voice.sqlite3'):
                profile = voice_profiles.manage({
                    'operation': 'create', 'name': 'Test Person', 'consent': True
                })['profiles'][0]['id']
                with patch.object(voice_profiles, 'validate_audio',
                                  return_value=(b'test-audio', 1.0)):
                    saved = voice_profiles.manage({
                        'operation': 'save_sample', 'profile': profile,
                        'consent': True, 'audio': 'test'
                    })
                sample = saved['profiles'][0]['samples'][0]['id']
                with patch.object(voice_profiles, 'sanitize_retained_voice_snapshots',
                                  return_value=1) as scrub:
                    deleted = voice_profiles.manage({
                        'operation': 'delete_sample', 'profile': profile,
                        'sample': sample, 'confirm': True
                    })
                    self.assertFalse(deleted['backup_cleanup_required'])
                    scrub.assert_called_once_with(Path(temp))
                    scrub.reset_mock()
                    voice_profiles.manage({
                        'operation': 'delete_profile', 'profile': profile, 'confirm': True
                    })
                    scrub.assert_called_once_with(Path(temp))

    def test_cleanup_failure_keeps_deletion_and_reports_operator_action(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(voice_profiles, 'DATABASE', Path(temp) / 'voice.sqlite3'):
                profile = voice_profiles.manage({
                    'operation': 'create', 'name': 'Test Person', 'consent': True
                })['profiles'][0]['id']
                with patch.object(voice_profiles, 'sanitize_retained_voice_snapshots',
                                  side_effect=ValueError('secret-private-test-path')), \
                     patch.object(voice_profiles, '_LOGGER') as logger:
                    result = voice_profiles.manage({
                        'operation': 'revoke_consent', 'profile': profile, 'confirm': True
                    })
                self.assertTrue(result['backup_cleanup_required'])
                self.assertIn('could not be sanitised', result['notice'])
                self.assertNotIn('secret-private-test-path', str(result))
                self.assertIsNone(result['profiles'][0]['consent_at'])
                logger.warning.assert_called_once_with(
                    'Retained voice backup cleanup needs operator review (reason=%s)',
                    'ValueError')
                self.assertNotIn('secret-private-test-path', str(logger.warning.call_args))

    def test_revocation_requires_explicit_confirmation(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(voice_profiles, 'DATABASE', Path(temp) / 'voice.sqlite3'):
                profile = voice_profiles.manage({'operation': 'create', 'name': 'Test Person', 'consent': True})['profiles'][0]['id']
                with self.assertRaises(ValueError):
                    voice_profiles.manage({'operation': 'revoke_consent', 'profile': profile})
                self.assertIsNotNone(voice_profiles.listing()['profiles'][0]['consent_at'])


if __name__ == '__main__':
    unittest.main()
