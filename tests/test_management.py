"""Exercise management features against real temporary stores and HTTP boundaries."""
import base64
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
from pathlib import Path
import sqlite3
import struct
from tempfile import TemporaryDirectory
from threading import Thread
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import wave

import configuration
import diagnostics
import history
import music
import server
import state_backup
import voice_profiles


def wav(seconds=1, value=1000, rate=16000):
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(struct.pack('<h', value) * int(seconds * rate))
    return base64.b64encode(stream.getvalue()).decode()


class ManagementTests(TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(TemporaryDirectory()))
        for module, name in ((history, 'history'), (diagnostics, 'diagnostics'), (voice_profiles, 'voice-profiles')):
            self.enterContext(patch.object(module, 'DATABASE', self.directory / (name + '.sqlite3')))

    def missed(self):
        history.record('test', 'assist', 'End 60 time.', 'Try again.')
        return history.recent()[0]['id']

    def test_intention_edits_persist_and_stale_tabs_cannot_overwrite(self):
        history.teach_intent(self.missed(), 'end sexy time', 'Try again.')
        history.edit_intent('end 60 time', 'stop sexy time', 'end sexy time')
        self.assertEqual(history.learned_intent('end 60 time'), 'stop sexy time')
        for values in [('end 60 time', 'dinner time', 'end sexy time'),
                       ('missing', 'dinner time', 'none'), ('end 60 time', 'End 60 time.', 'stop sexy time'),
                       ('end 60 time', 'x' * 121, 'stop sexy time'), (None, 'foo', 'bar')]:
            with self.assertRaises(ValueError):
                history.edit_intent(*values)
        self.assertEqual(len(history.recent()), 1)

    def test_export_is_private_by_default_and_preview_does_not_apply(self):
        history.teach_intent(self.missed(), 'end sexy time', 'Try again.')
        with patch.dict(os.environ, {'DECLAN_HA_TOKEN': 'never-export', 'DECLAN_SPOTIFY_CLIENT_SECRET': 'private',
                                     'DECLAN_GOOD_MORNING_SCRIPT': 'script.morning'}):
            document = configuration.export()
            self.assertNotIn('learned_intents', document)
            self.assertNotIn('never-export', json.dumps(document))
            self.assertNotIn('private', json.dumps(document))
            self.assertEqual(document['settings']['DECLAN_GOOD_MORNING_SCRIPT'], 'script.morning')
            document['settings']['DECLAN_GOOD_MORNING_SCRIPT'] = 'script.changed'
            preview = configuration.preview(document)
            self.assertEqual(configuration.get('DECLAN_GOOD_MORNING_SCRIPT'), 'script.morning')
            self.assertFalse(preview['replaces_learning'])
            configuration.apply(document, preview['expected'])
            self.assertEqual(configuration.get('DECLAN_GOOD_MORNING_SCRIPT'), 'script.changed')
            self.assertEqual(configuration.get('DECLAN_HA_TOKEN'), 'never-export')
            self.assertEqual(history.learned_intent('end 60 time'), 'end sexy time')
            previous = configuration.recovery()
            configuration.apply(previous, configuration.preview(previous)['expected'])
            self.assertEqual(configuration.get('DECLAN_GOOD_MORNING_SCRIPT'), 'script.morning')

    def test_import_is_transactional_versioned_and_rejects_unreviewed_changes(self):
        document = {'format': 'declan-settings', 'schema_version': 1,
                    'settings': {'DECLAN_MOVIE_SCRIPT': 'script.movie'}, 'learned_intents': {'movie please': 'movie time'}}
        preview = configuration.preview(document)
        configuration.apply(document, preview['expected'])
        self.assertEqual(history.learned_intents(), {'movie please': 'movie time'})
        with self.assertRaises(ValueError):
            configuration.apply(document, preview['expected'])
        invalid = [None, {**document, 'schema_version': 2}, {**document, 'token': 'secret'},
                   {**document, 'settings': {'DECLAN_HA_TOKEN': 'secret'}},
                   {**document, 'settings': {'DECLAN_MOVIE_SCRIPT': 'light.wrong'}},
                   {**document, 'learned_intents': {'same': 'same'}},
                   {**document, 'learned_intents': {'UPPER': 'lower'}},
                   {**document, 'learned_intents': {'phrase': 123}}]
        for item in invalid:
            with self.assertRaises(ValueError):
                configuration.preview(item)
        self.assertEqual(configuration.get('DECLAN_MOVIE_SCRIPT'), 'script.movie')
        with history.database() as db:
            db.execute('DELETE FROM settings_recovery')
        with self.assertRaises(ValueError):
            configuration.recovery()

    def test_snapshot_includes_committed_wal_data_and_rejects_corrupt_storage(self):
        history.teach_intent(self.missed(), 'end sexy time', 'Try again.')
        with closing(sqlite3.connect(history.DATABASE)) as db, db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute("INSERT INTO learned_intents VALUES ('dinner please', 'dinner time')")
            db.commit()
            (self.directory / 'spotify-settings.json').write_text('{"client_secret":"local-only"}')
            name = state_backup.snapshot(self.directory)
            saved = self.directory / 'upgrade-backups' / name
            with closing(sqlite3.connect(saved / history.DATABASE.name)) as copy, copy:
                self.assertEqual(copy.execute('SELECT count(*) FROM learned_intents').fetchone()[0], 2)
            self.assertIn('local-only', (saved / 'spotify-settings.json').read_text())
            if os.name == 'posix':
                self.assertEqual((saved.stat().st_mode & 0o777), 0o700)
                self.assertEqual(((saved / history.DATABASE.name).stat().st_mode & 0o777), 0o600)
        (self.directory / 'broken.sqlite3').write_bytes(b'broken database')
        with self.assertRaises((ValueError, sqlite3.Error)):
            state_backup.snapshot(self.directory)
        (self.directory / 'broken.sqlite3').unlink()
        (self.directory / 'spotify-settings.json').write_text('[]')
        with self.assertRaises(ValueError):
            state_backup.check(self.directory)

    def test_diagnostics_isolate_concurrent_requests_and_redact_provider_errors(self):
        def work(number):
            with diagnostics.request('/api/chat') as trace:
                with diagnostics.stage('spotify_search'):
                    if number == 1:
                        raise ValueError('Authorization: secret transcript and token')
                trace['outcome'] = 'confirmed'
                return diagnostics.current_id()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda n: self.capture(work, n), [0, 1]))
        self.assertIsNone(diagnostics.current_id())
        traces = diagnostics.recent()
        self.assertEqual(len(traces), 2)
        self.assertEqual({trace['outcome'] for trace in traces}, {'confirmed', 'failed'})
        encoded = json.dumps(traces)
        self.assertNotIn('secret', encoded)
        self.assertNotIn('transcript', encoded)
        self.assertNotEqual(traces[0]['id'], traces[1]['id'])
        self.assertIn('ValueError', encoded)
        self.assertTrue(results[0])

    @staticmethod
    def capture(function, value):
        try:
            return function(value)
        except ValueError:
            return None

    def test_diagnostic_stage_outcomes_retention_and_storage_failure(self):
        self.assertEqual(diagnostics.recent(), [])
        with diagnostics.request('/api/assist'):
            self.assertFalse(diagnostics.timed('verification')(lambda: False)())
            self.assertEqual(diagnostics.timed('music')(lambda: ('No match', 'unavailable'))()[1], 'unavailable')
        with closing(sqlite3.connect(diagnostics.DATABASE)) as db, db:
            db.execute('INSERT INTO traces VALUES (?, ?, ?)', ('expired', 0, '{}'))
            db.executemany('INSERT INTO traces VALUES (?, ?, ?)', [(str(n), 1, '{}') for n in range(505)])
        with diagnostics.request('/api/chat'):
            pass
        with closing(sqlite3.connect(diagnostics.DATABASE)) as db, db:
            self.assertEqual(db.execute('SELECT count(*) FROM traces').fetchone()[0], 2)
        with patch.object(diagnostics, 'DATABASE', self.directory / 'no-parent' / 'bad' / 'trace.db'), patch.object(
            diagnostics.Path, 'mkdir', side_effect=OSError):
            with diagnostics.request('/api/chat'):
                self.assertTrue(True)

    def test_voice_samples_require_consent_review_and_can_be_exported_and_deleted(self):
        self.assertEqual(voice_profiles.listing()['profiles'], [])
        for body in ({'operation': 'create', 'name': 'Jaco'}, {'operation': 'create', 'name': '../bad', 'consent': True}):
            with self.assertRaises(ValueError):
                voice_profiles.manage(body)
        result = voice_profiles.manage({'operation': 'create', 'name': 'Jaco', 'consent': True})
        profile = result['profiles'][0]['id']
        data = wav()
        save = {'operation': 'save_sample', 'profile': profile, 'consent': True, 'audio': data}
        result = voice_profiles.manage(save)
        self.assertFalse(result['recogniser_connected'])
        sample = result['profiles'][0]['samples'][0]['id']
        for operation in ('preview', 'export'):
            exported = voice_profiles.manage({'operation': operation, 'profile': profile, 'sample': sample})
            self.assertEqual(exported['samples'][0]['audio'], data)
        for body in (save, {**save, 'consent': False}, {'operation': 'create', 'name': 'Jaco', 'consent': True},
                     {'operation': 'delete_profile', 'profile': profile},
                     {'operation': 'delete_sample', 'profile': profile, 'sample': 'wrong', 'confirm': True}):
            with self.assertRaises(ValueError):
                voice_profiles.manage(body)
        voice_profiles.manage({'operation': 'delete_sample', 'profile': profile, 'sample': sample, 'confirm': True})
        voice_profiles.manage(save)
        voice_profiles.manage({'operation': 'delete_profile', 'profile': profile, 'confirm': True})
        self.assertEqual(voice_profiles.listing()['profiles'], [])
        with closing(sqlite3.connect(voice_profiles.DATABASE)) as db, db:
            self.assertEqual(db.execute('SELECT count(*) FROM samples').fetchone()[0], 0)
        with self.assertRaises(ValueError):
            voice_profiles.manage(save)

    def test_voice_recordings_reject_silence_wrong_format_and_unbounded_samples(self):
        for audio in (None, 'not base64!', base64.b64encode(b'not wav').decode(), wav(value=0),
                      wav(rate=8000), wav(seconds=0.1), wav(seconds=11), 'A' * 427001):
            with self.assertRaises(ValueError):
                voice_profiles.validate_audio(audio)
        profile = voice_profiles.manage({'operation': 'create', 'name': 'Edd', 'consent': True})['profiles'][0]['id']
        with voice_profiles.database() as db:
            db.executemany('INSERT INTO samples VALUES (?, ?, ?, ?, ?, ?)',
                           [(str(n), profile, b'placeholder', 1, str(n), 0) for n in range(20)])
        with self.assertRaises(ValueError):
            voice_profiles.manage({'operation': 'save_sample', 'profile': profile, 'audio': wav(), 'consent': True})
        with voice_profiles.database() as db:
            db.executemany('INSERT INTO profiles VALUES (?, ?, ?)', [(str(n), 'Person' + str(n), 0) for n in range(9)])
        with self.assertRaises(ValueError):
            voice_profiles.manage({'operation': 'create', 'name': 'Another', 'consent': True})


class ManagementAPITests(TestCase):
    def setUp(self):
        directory = Path(self.enterContext(TemporaryDirectory()))
        for module, name in ((history, 'history'), (diagnostics, 'diagnostics'), (voice_profiles, 'voices')):
            self.enterContext(patch.object(module, 'DATABASE', directory / (name + '.sqlite3')))
        http = self.enterContext(server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler))
        worker = Thread(target=http.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(worker.join)
        self.addCleanup(http.shutdown)
        self.origin = f'http://127.0.0.1:{http.server_port}'

    def request(self, path, body=None, origin=True, headers=None):
        headers = headers or {}
        if origin:
            headers.update({'Origin': self.origin, 'Content-Type': 'application/json'})
        try:
            with urlopen(Request(self.origin + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers=headers), timeout=4) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            with error:
                return error.code, json.load(error)

    def test_management_operations_need_browser_origin_and_never_dispatch_household_actions(self):
        for path, body in (('/api/settings/import', {'document': configuration.export()}),
                           ('/api/voice-profiles', {'operation': 'create', 'name': 'Jaco', 'consent': True}),
                           ('/api/history/intents', {'phrase': 'a', 'target': 'b', 'previous': 'c'})):
            self.assertEqual(self.request(path, body, origin=False)[0], 403)
        with patch.object(server, 'ha_device_connection', side_effect=AssertionError('No HA action expected')):
            status, export = self.request('/api/settings/export')
            self.assertEqual(status, 200)
            status, preview = self.request('/api/settings/import', {'document': export})
            self.assertEqual(status, 200)
            self.assertEqual(self.request('/api/settings/import', {'document': export, 'expected': preview['expected'], 'confirm': True})[0], 200)
            self.assertEqual(self.request('/api/settings/import', {'confirm': True})[0], 400)
            self.assertEqual(self.request('/api/voice-profiles', {'operation': 'create', 'name': 'Jaco', 'consent': True})[0], 200)
            self.assertEqual(self.request('/api/voice-profiles')[1]['profiles'][0]['name'], 'Jaco')
            self.assertEqual(self.request('/api/voice-profiles', {'operation': 'create'})[0], 400)
        self.assertEqual(self.request('/api/diagnostics')[1], {'traces': []})
        self.assertEqual(self.request('/api/diagnostics', headers={'Host': 'attacker.invalid'})[0], 403)

    def test_request_ids_link_history_and_diagnostics_without_copying_messages(self):
        with patch.object(server, 'read_guest_mode', return_value='off'):
            status, result = self.request('/api/chat', {'message': 'Hello Declan'})
        self.assertEqual(status, 200)
        traces = self.request('/api/diagnostics')[1]['traces']
        self.assertEqual(traces[0]['id'], result['diagnostic_id'])
        self.assertEqual(history.recent()[0]['diagnostic_id'], result['diagnostic_id'])
        self.assertNotIn('Hello Declan', json.dumps(traces))
