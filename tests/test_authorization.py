"""Exercise the actual HTTP handler using in-memory sockets and isolated state."""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import json
import math
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from authorization import Policy, RoutineAuthorizer
import server


class MemorySocket:
    def __init__(self, data):
        self.input = BytesIO(data)
        self.output = bytearray()

    def makefile(self, *args):
        return self.input

    def sendall(self, data):
        self.output.extend(data)

    def settimeout(self, value):
        pass


class AuthorizationTests(TestCase):
    def setUp(self):
        self.enterContext(patch.dict(os.environ, {
            'DECLAN_ASSIST_TOKEN': 'test', 'DECLAN_SENSITIVE_ROUTINES': 'night,guest',
            'DECLAN_ROUTINE_SPEAKERS': '', 'DECLAN_ROUTINE_SPEAKER_CONFIDENCE': '0.9',
        }))
        root = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(patch.object(server.history, 'DATABASE', root / 'history.sqlite3'))
        self.enterContext(patch.object(server.diagnostics, 'DATABASE', root / 'diagnostics.sqlite3'))
        self.enterContext(patch.object(server.Handler, 'log_message'))
        self.enterContext(patch.object(server, 'SESSIONS', OrderedDict()))
        self.now = [100]
        self.authorizer = RoutineAuthorizer(clock=lambda: self.now[0])
        self.enterContext(patch.object(server, 'ROUTINE_AUTHORIZER', self.authorizer))
        self.routine = self.enterContext(patch.object(server, 'execute_routine', return_value=('Ran routine.', 'confirmed', None)))
        self.guest = self.enterContext(patch.object(server, 'guest_assignment', return_value=('Changed guests.', 'confirmed')))
        self.light = self.enterContext(patch.object(server, 'handle_light_request', return_value=('Lights changed.', 'confirmed')))
        self.timer = self.enterContext(patch.object(server.timers, 'handle', return_value=None))
        self.enterContext(patch.object(server, 'ha_device_connection', return_value=None))
        self.enterContext(patch.object(server, 'read_guest_mode', return_value='off'))

    def ask(self, message, session=None, *, device='device', satellite='assist_satellite.test',
            speaker=None, path='/api/assist', source=None):
        body = json.dumps({'message': message, 'session_id': session, 'device_id': device,
                           'satellite_id': satellite, 'speaker': speaker, 'source': source}).encode()
        headers = (f'POST {path} HTTP/1.0\r\nHost: 127.0.0.1:8765\r\nOrigin: http://127.0.0.1:8765\r\n'
                   f'Authorization: Bearer test\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n')
        socket = MemorySocket(headers.encode() + body)
        # PR #29 adds throttling to the server fixture; these requests have valid credentials.
        http = SimpleNamespace(server_port=8765, bad_tokens=SimpleNamespace(check=lambda peer, valid: 0))
        server.Handler(socket, ('127.0.0.1', 1234), http)
        head, _, payload = bytes(socket.output).partition(b'\r\n\r\n')
        self.assertIn(b'200 OK', head, payload)
        return json.loads(payload)

    def confirm(self, prompt, **kwargs):
        command = re.search(r'"(confirm routine [0-9 ]+)"', prompt['reply'])[1]
        return self.ask(command, prompt['session_id'], **kwargs)

    def test_unknown_request_has_no_side_effect_and_confirmation_executes_once(self):
        prompt = self.ask('good night')
        self.assertEqual(prompt['outcome'], 'confirmation_required')
        self.assertTrue(prompt['continue_conversation'])
        for action in (self.routine, self.guest, self.light, self.timer):
            action.assert_not_called()
        result = self.confirm(prompt)
        self.assertEqual(result['authorization'], 'spoken_confirmation')
        self.assertEqual(result['outcome'], 'confirmed')
        self.routine.assert_called_once_with(('night', {}), [])
        self.assertNotIn('continue_conversation', result)
        self.assertEqual(self.confirm(prompt)['outcome'], 'confirmation_invalid')
        self.routine.assert_called_once()
        turns = server.history.recent()
        self.assertEqual([t['outcome'] for t in turns], ['confirmation_invalid', 'confirmed', 'confirmation_required'])

    def test_exact_allow_list_and_well_formed_recognition_required(self):
        valid = {'name': 'Test Owner', 'confidence': .95, 'interaction_id': 'live-match'}
        with patch.dict(os.environ, {'DECLAN_ROUTINE_SPEAKERS': 'Test Owner'}):
            for bad in (None, {}, {**valid, 'confidence': .89}, {**valid, 'confidence': True},
                        {**valid, 'confidence': math.nan}, {**valid, 'confidence': 1.1},
                        {**valid, 'confidence': 10 ** 400},
                        {**valid, 'interaction_id': ''}, {**valid, 'name': 'Guest'},
                        {**valid, 'name': 'Unknown'}):
                with self.subTest(speaker=bad):
                    self.assertEqual(self.ask('good night', speaker=bad)['outcome'], 'confirmation_required')
            self.routine.assert_not_called()
            result = self.ask('good night', speaker={**valid, 'name': 'test owner'})
            self.assertEqual(result['authorization'], 'recognised_speaker')
            self.routine.assert_called_once()

    def test_cross_origin_source_session_expiry_and_wrong_confirmation_fail(self):
        for change in ({'device': 'other'}, {'satellite': 'assist_satellite.other'},
                       {'path': '/api/chat', 'source': 'voice'}):
            prompt = self.ask('good night')
            self.assertEqual(self.confirm(prompt, **change)['outcome'], 'confirmation_invalid')
        prompt = self.ask('good night')
        command = re.search(r'"(confirm routine [0-9 ]+)"', prompt['reply'])[1]
        self.assertEqual(self.ask(command, 'unknown-session')['outcome'], 'confirmation_invalid')
        self.now[0] += 30
        self.assertEqual(self.confirm(prompt)['outcome'], 'confirmation_invalid')
        prompt = self.ask('good night')
        self.assertEqual(self.ask('confirm routine wrong', prompt['session_id'])['outcome'], 'confirmation_invalid')
        self.assertEqual(self.confirm(prompt)['outcome'], 'confirmation_invalid')
        self.routine.assert_not_called()

    def test_cancel_intervening_command_and_policy_change_invalidate_confirmation(self):
        for cancel in ('cancel routine', 'no', 'hello'):
            prompt = self.ask('good night')
            self.ask(cancel, prompt['session_id'])
            self.assertEqual(self.confirm(prompt)['outcome'], 'confirmation_invalid')
        prompt = self.ask('good night')
        with patch.dict(os.environ, {'DECLAN_ROUTINE_SPEAKER_CONFIDENCE': '.95'}):
            self.assertEqual(self.confirm(prompt)['outcome'], 'confirmation_invalid')
        self.routine.assert_not_called()

    def test_replacement_prompt_never_reuses_the_previous_code_and_words_are_supported(self):
        with patch('authorization.secrets.randbelow', return_value=1234):
            first = self.ask('good night')
            replacement = self.ask('the guests have left', first['session_id'])
        self.assertIn('1 2 3 5', replacement['reply'])
        self.assertEqual(self.confirm(first)['outcome'], 'confirmation_invalid')
        self.assertEqual(self.confirm(replacement)['outcome'], 'confirmation_invalid')
        self.routine.assert_not_called()
        self.guest.assert_not_called()
        with patch('authorization.secrets.randbelow', return_value=1234):
            prompt = self.ask('good night')
        result = self.ask('confirm routine one two three four', prompt['session_id'])
        self.assertEqual(result['authorization'], 'spoken_confirmation')
        self.routine.assert_called_once()

    def test_learned_intention_and_chained_lights_are_one_bound_request(self):
        with server.history.database() as db:
            db.execute("INSERT INTO learned_intents VALUES ('sleepy', 'good night and turn off the lights')")
        prompt = self.ask('sleepy')
        self.assertIn('good night and turn off the lights', prompt['reply'])
        self.routine.assert_not_called()
        self.light.assert_not_called()
        # Editing learning after the prompt must not change what was confirmed.
        with server.history.database() as db:
            db.execute("UPDATE learned_intents SET target='good morning' WHERE phrase='sleepy'")
        self.confirm(prompt)
        self.routine.assert_called_once_with(('night', {}), [])
        self.assertEqual(self.light.call_args.args[0], 'turn off the lights')

    def test_keyboard_is_trusted_browser_voice_requires_confirmation_and_cannot_spoof_speaker(self):
        valid = {'name': 'Test Owner', 'confidence': 1, 'interaction_id': 'match'}
        with patch.dict(os.environ, {'DECLAN_ROUTINE_SPEAKERS': 'Test Owner'}):
            prompt = self.ask('good night', path='/api/chat', source='voice', speaker=valid)
            self.assertEqual(prompt['outcome'], 'confirmation_required')
            self.routine.assert_not_called()
            self.confirm(prompt, path='/api/chat', source='voice')
            self.assertEqual(self.ask('good night', path='/api/chat')['authorization'], 'trusted_browser')
            self.assertEqual(self.routine.call_count, 2)

    def test_missing_physical_origin_is_blocked_but_read_only_guest_query_is_allowed(self):
        self.assertEqual(self.ask('good night', device=None, satellite=None)['outcome'], 'authorization_unavailable')
        self.routine.assert_not_called()
        self.ask('who is in charge')
        self.guest.assert_called_once()
        self.guest.reset_mock()
        self.assertEqual(self.ask('the guests have left')['outcome'], 'confirmation_required')
        self.guest.assert_not_called()

    def test_supported_groups_can_be_protected_without_area_or_device_requests(self):
        for phrase, kind in (('good morning', 'morning'), ('good night', 'night'),
                             ('movie time in here', 'movie'), ('open netflix in the bedroom', 'movie'),
                             ('dinner time', 'dinner'), ('sexy time', 'sexy_time'),
                             ('the guests have left', 'guest')):
            with self.subTest(phrase=phrase):
                self.assertEqual(server.routine_kind(phrase), kind)
        self.assertIsNone(server.routine_kind('who is in charge'))
        self.assertIsNone(server.routine_kind('turn off a light'))
        with patch.dict(os.environ, {'DECLAN_SENSITIVE_ROUTINES': 'morning,movie,sexy_time,dinner'}):
            for phrase in ('good morning', 'movie time in here', 'sexy time', 'dinner time'):
                self.assertEqual(self.ask(phrase)['outcome'], 'confirmation_required')
        for action in (self.routine, self.guest, self.light, self.timer):
            action.assert_not_called()

    def test_configuration_errors_fail_closed_and_explicit_none_disables_protection(self):
        for env in ({'DECLAN_SENSITIVE_ROUTINES': ''}, {'DECLAN_SENSITIVE_ROUTINES': 'nigth'},
                    {'DECLAN_ROUTINE_SPEAKERS': 'Unknown'}, {'DECLAN_ROUTINE_SPEAKERS': 'Owner,'},
                    {'DECLAN_ROUTINE_SPEAKER_CONFIDENCE': 'nan'}, {'DECLAN_ROUTINE_SPEAKER_CONFIDENCE': '.5'}):
            with self.subTest(env=env), patch.dict(os.environ, env):
                with self.assertRaises(ValueError):
                    Policy.from_env()
                self.assertEqual(self.ask('good night')['outcome'], 'authorization_unavailable')
        self.routine.assert_not_called()
        with patch.dict(os.environ, {'DECLAN_SENSITIVE_ROUTINES': 'none'}):
            self.ask('good night')
        self.routine.assert_called_once()

    def test_confirmation_capacity_is_bounded_and_concurrent_replay_claims_once(self):
        self.authorizer.capacity = 1
        prompt = self.ask('good night')
        self.assertEqual(self.ask('good night')['outcome'], 'authorization_unavailable')
        key, item = next(iter(self.authorizer.pending.items()))
        command = 'confirm routine ' + item['code']
        source, session, scope = key
        def confirm(_):
            return self.authorizer.check(command, command, source=source, session=session, scope=scope,
                                         bindable=True, speaker=None, kind_for=server.routine_kind)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(confirm, range(20)))
        self.assertEqual(sum(r.authority == 'spoken_confirmation' for r in results), 1)
        self.assertEqual(sum(r.outcome == 'confirmation_invalid' for r in results), 19)
        self.now[0] += 30
        self.assertEqual(self.ask('good night')['outcome'], 'confirmation_required')
