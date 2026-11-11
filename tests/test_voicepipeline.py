"""VoicePipeline contract fixtures derived from the owner's deployed API and helpers."""
import io
import json
import os
from unittest import TestCase
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

import voicepipeline as vp

SPEAKERS = [{'id': 'speaker-jaco', 'name': 'Jaco', 'reference_clip_count': 3},
            {'id': 'speaker-ed', 'name': 'Ed', 'reference_clip_count': 5}]
PENDING = [{'id': 'interaction-1', 'status': 'pending', 'transcript': 'Hello',
            'audio_url': 'http://untrusted.invalid/audio'}]


class PipelineTests(TestCase):
    def setUp(self):
        self.calls = []
        self.responses = {'/api/v1/speakers': SPEAKERS, '/api/v1/interactions/pending': PENDING,
                          '/api/v1/interactions/history': [{'id': 'history-1', 'current_resolution_id': 'r1'}]}

    def fake(self, method, path, body=None, **kwargs):
        self.calls.append((method, path, body))
        return self.responses.get(path, {})

    def change(self, **overrides):
        return {'operation': 'resolve', 'action': 'assign', 'interaction_id': 'interaction-1',
                'assigned_to': 'Ed', 'consent': True, 'confirm': True, **overrides}

    def test_list_uses_existing_profiles_and_never_returns_upstream_audio_urls(self):
        with patch.object(vp, 'request', side_effect=self.fake):
            result = vp.listing()
            self.assertEqual(result['profiles'][1]['name'], 'Ed')
            self.assertNotIn('audio_url', result['interactions'][0])
            self.assertEqual(self.calls, [('GET', '/api/v1/speakers', None),
                                          ('GET', '/api/v1/interactions/pending', None)])
            self.assertEqual(vp.manage({'operation': 'history'})['interactions'][0]['current_resolution_id'], 'r1')

    def test_assign_and_enrol_use_exact_names_and_one_write_without_transcribing(self):
        with patch.object(vp, 'request', side_effect=self.fake):
            for body in (self.change(), self.change(action='confirm'), self.change(action='enrol', assigned_to='Edd')):
                self.assertTrue(vp.manage(body)['saved'])
                self.assertEqual(self.calls[-1], ('POST', '/api/v1/interactions/interaction-1/resolve',
                                 {'action': body['action'], 'assigned_to': body['assigned_to']}))
            with self.assertRaises(ValueError):
                vp.manage(self.change(assigned_to='Edd'))  # Display alias is not an enrolled name.
            with self.assertRaises(ValueError):
                vp.manage(self.change(action='enrol', assigned_to='ed'))

    def test_no_writes_without_explicit_permission_confirmation_and_pending_entry(self):
        with patch.object(vp, 'request', side_effect=self.fake):
            for body in (None, {}, self.change(confirm=False), self.change(consent=False),
                         self.change(action='arbitrary'), self.change(assigned_to='Unknown'),
                         self.change(assigned_to='../bad'), self.change(interaction_id='../bad')):
                with self.assertRaises(ValueError):
                    vp.manage(body)
            self.responses['/api/v1/interactions/pending'] = []
            with self.assertRaises(vp.PipelineError) as error:
                vp.manage(self.change())
            self.assertEqual(error.exception.status, 409)
            self.assertTrue(all(method == 'GET' for method, _, _ in self.calls))

    def test_correction_forwards_stale_edit_token_and_never_adds_a_reference(self):
        with patch.object(vp, 'request', side_effect=self.fake):
            body = self.change(operation='correct', expected_resolution_id='resolution-1')
            vp.manage(body)
            self.assertEqual(self.calls[-1], ('POST', '/api/v1/interactions/interaction-1/correct',
                                             {'assigned_to': 'Ed', 'expected_resolution_id': 'resolution-1'}))
            vp.manage({**body, 'assigned_to': None, 'consent': False})
            self.assertIsNone(self.calls[-1][2]['assigned_to'])
            with self.assertRaises(ValueError):
                vp.manage(self.change(operation='correct'))
            with self.assertRaises(ValueError):
                vp.manage({**body, 'expected_resolution_id': '../bad'})
            self.assertFalse(any(path.endswith('/resolve') for _, path, _ in self.calls))

    def test_dismiss_delete_and_clear_have_distinct_remote_operations(self):
        with patch.object(vp, 'request', side_effect=self.fake):
            vp.manage(self.change(action='dismiss', consent=False))
            self.assertEqual(self.calls[-1][2], {'action': 'dismiss', 'assigned_to': None})
            for operation, method, suffix in [('delete_speaker', 'DELETE', ''), ('clear_clips', 'POST', '/clear-clips')]:
                vp.manage({'operation': operation, 'speaker_id': 'speaker-ed', 'confirm': True})
                self.assertEqual(self.calls[-1], (method, '/api/v1/speakers/speaker-ed' + suffix, None))
            with self.assertRaises(ValueError):
                vp.manage({'operation': 'delete_speaker', 'speaker_id': 'gone', 'confirm': True})
            vp.manage({'operation': 'audio', 'interaction_id': 'interaction-1'})
            self.assertEqual(self.calls[-1][:2], ('GET', '/api/v1/audio/interaction-1'))
            self.responses['/api/v1/speakers'] = {}
            with self.assertRaises(vp.PipelineError):
                vp.speakers()


class TransportTests(TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {'DECLAN_VOICEPIPELINE_URL': 'http://192.168.0.43:8000',
                                                 'DECLAN_VOICEPIPELINE_TOKEN': 'private-key'}))
        self.opener = self.enterContext(patch.object(vp, 'build_opener')).return_value
        self.response = self.opener.open.return_value.__enter__.return_value
        self.response.read.return_value = b'[]'

    def test_fixed_destination_no_proxy_no_redirect_and_private_server_token(self):
        self.assertEqual(vp.request('GET', '/api/v1/speakers'), [])
        req = self.opener.open.call_args.args[0]
        self.assertEqual(req.full_url, 'http://192.168.0.43:8000/api/v1/speakers')
        self.assertEqual(req.get_header('Authorization'), 'Bearer private-key')
        self.assertEqual(self.opener.open.call_args.kwargs['timeout'], 8)
        self.assertIsNone(vp.NoRedirect().redirect_request(None, None, None, None, None, None))
        vp.request('POST', '/api/v1/test', {'action': 'assign'})
        self.assertEqual(json.loads(self.opener.open.call_args.args[0].data), {'action': 'assign'})
        self.response.read.return_value = b''
        self.assertEqual(vp.request('DELETE', '/api/v1/test'), {})

    def test_bad_configuration_and_protocol_errors_are_bounded_and_redacted(self):
        for base in ('', 'file:///tmp/x', 'http://user:pass@host', 'http://host/path', 'http://host?key=secret', 'http://['):
            with patch.dict(os.environ, {'DECLAN_VOICEPIPELINE_URL': base}), self.assertRaises(vp.PipelineError):
                vp.request('GET', '/api/v1/speakers')
        for raw in (b'invalid json', b'x' * (vp.MAX_RESPONSE + 1)):
            self.response.read.return_value = raw
            with self.assertRaises(vp.PipelineError):
                vp.request('GET', '/api/v1/speakers')
        for raw in (b'not a wave', b'RIFF0000oops'):
            self.response.read.return_value = raw
            with self.assertRaises(vp.PipelineError):
                vp.request('GET', '/api/v1/audio/test', audio=True)
        self.response.read.return_value = b'RIFF0000WAVEdata'
        self.assertIn('audio', vp.request('GET', '/api/v1/audio/test', audio=True))

    def test_remote_conflicts_errors_and_lost_write_responses_never_retry(self):
        for code, status in ((409, 409), (404, 404), (422, 502), (302, 502), (500, 502)):
            self.opener.open.reset_mock()
            self.opener.open.side_effect = HTTPError('url', code, 'private message', {}, io.BytesIO(b'secret'))
            with self.assertRaises(vp.PipelineError) as error:
                vp.request('POST', '/api/v1/test', {})
            self.assertEqual(error.exception.status, status)
            self.assertNotIn('secret', str(error.exception))
            self.opener.open.assert_called_once()
        self.opener.open.side_effect = URLError('private internal detail')
        with self.assertRaisesRegex(vp.PipelineError, 'Refresh before retrying'):
            vp.request('POST', '/api/v1/test', {})
