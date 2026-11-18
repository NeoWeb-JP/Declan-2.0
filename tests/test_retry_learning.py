"""Exercise retry learning through the real handler without external services."""
import io
import json
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import history
import retry_learning
import server


class RetryLearningTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(history, 'DATABASE', Path(directory) / 'history.db'))
        self.enterContext(patch.object(server, "SESSION_STORE", server.session_store.SessionStore()))
        self.enterContext(patch.object(server, 'read_guest_mode', return_value='off'))
        self.enterContext(patch.object(server, 'read_visitors_present', return_value=False))
        self.enterContext(patch.object(server, 'guarded_openai_fallback_result', return_value=None))
        self.enterContext(patch.object(server, 'select_routine_turn_result', return_value=None))
        self.enterContext(patch.object(server, 'handle_light_request_result', return_value=None))
        self.enterContext(patch.object(server, 'search_media', return_value=None))
        self.enterContext(patch.object(server.CAPTURE_ARBITER, 'claim', return_value=True))
        self.enterContext(patch.dict(server.os.environ, {'DECLAN_ASSIST_TOKEN': 'test'}))

    def ask(self, message, session=None, device='kitchen', path='/api/assist', expected_status=200, **extra):
        handler = object.__new__(server.Handler)
        handler.path = path
        body = json.dumps(extra if path.startswith('/api/native/') else
                          dict(message=message, session_id=session, device_id=device, **extra)).encode()
        handler.rfile = io.BytesIO(body)
        handler.headers = Message()
        for key, value in {'Content-Type':'application/json', 'Content-Length':str(len(body)),
                           'Authorization':'Bearer test'}.items():
            handler.headers[key] = value
        handler.server = SimpleNamespace(bad_tokens=SimpleNamespace(check=lambda *args: 0))
        handler.client_address = ('127.0.0.1', 1)
        handler.has_ingress_access = lambda: True
        handler.send_json = Mock()
        handler.log_error = Mock()
        handler.handle_post()
        status, result = handler.send_json.call_args.args
        self.assertEqual(status, expected_status, result)
        return result

    def succeed(self):
        return patch.object(server, 'handle_light_request_result', return_value=('Done', 'confirmed'))

    def test_successful_similar_retry_learns_and_preserves_both_responses(self):
        first = self.ask('office light on it', speaker={'interaction_id':'clip', 'name':'Unknown', 'confidence':0.1})
        self.assertTrue(first['continue_conversation'])
        with self.succeed():
            second = self.ask('office light on', first['session_id'])
        self.assertFalse(second['continue_conversation'])
        self.assertTrue(second['learned_from_retry'])
        self.assertEqual(history.learned_intent('office light on it'), 'office light on')
        turns = history.recent()
        self.assertEqual(turns[1]['reply'], server.UNMATCHED_REPLY)
        self.assertEqual(turns[1]['speaker_match']['interaction_id'], 'clip')
        self.assertTrue(turns[0]['reply'])
        with patch.object(server, 'handle_light_request_result', return_value=('Done','confirmed')) as handle:
            self.ask('office light on it')
        self.assertEqual(handle.call_args.args[0], 'office light on')

    def test_different_command_runs_without_learning(self):
        first = self.ask('office light on it')
        with self.succeed() as handle:
            second = self.ask('kitchen light on', first['session_id'])
        self.assertEqual(handle.call_args.args[0], 'kitchen light on')
        self.assertNotIn('learned_from_retry', second)
        self.assertEqual(history.learned_intents(), {})

    def test_cancel_and_stop_do_not_dispatch_or_learn(self):
        for cancel in ('cancel','stop','stop listening','never mind'):
            first = self.ask('office light on it')
            with self.succeed() as handle:
                result = self.ask(cancel, first['session_id'])
            handle.assert_not_called()
            self.assertEqual(result['reply'], '')
            self.assertFalse(result['continue_conversation'])
        self.assertEqual(history.learned_intents(), {})

    def test_expired_or_different_device_retry_does_not_learn(self):
        for expired in (True, False):
            first = self.ask('office light on it')
            if expired:
                server.SESSION_STORE.sessions[first['session_id']]['pending_retry']['at'] -= 31
            with self.succeed():
                self.ask('office light on', first['session_id'], device='kitchen' if expired else 'bedroom')
            self.assertEqual(history.learned_intents(), {})

    def test_failed_retry_does_not_learn_and_explicit_training_wins(self):
        first = self.ask('office light on it')
        self.ask('office light on', first['session_id'])
        self.assertEqual(history.learned_intents(), {})
        history.teach_phrase('office light on it', 'turn office light on')
        history.teach_phrase('office light on it', 'office light on', automatic=True)
        self.assertEqual(history.learned_intent('office light on it'), 'turn office light on')

    def test_teaching_any_source_does_not_execute(self):
        for source in ('assist', 'browser_voice', 'browser_keyboard', 'ha_sentence'):
            turn_id = history.record('s', source, source+' missed command', 'Could you rephrase?')
            history.teach_intent(turn_id, 'office light on', server.UNMATCHED_REPLY)
            self.assertEqual(history.learned_intent(source+' missed command'), 'office light on')

    def test_older_unlinked_recording_can_be_taught_without_executing_a_command(self):
        rows=[{'id':'old', 'transcript':'office light on it', 'status':'pending'}]
        with patch.object(server.voicepipeline,'interactions',return_value=rows), self.succeed() as dispatch:
            result=self.ask('unused',path='/api/native/intents',recording_id='old',target='office light on')
        # Management requests use their exact allowlisted shape.
        self.assertTrue(result['saved'])
        dispatch.assert_not_called()
        self.assertEqual(history.learned_intent('office light on it'),'office light on')

    def test_recording_review_statuses_preserve_teaching_and_rejection(self):
        for status, blocked in (("dismissed", True), ("rejected", True), ("discarded", True),
                                ("pending", False), ("resolved", False), ("future_status", False),
                                ("DISMISSED", False), (None, False)):
            with self.subTest(status=status):
                rows = [{'id': 'old', 'transcript': 'office light on it', 'status': status}]
                with patch.object(server.voicepipeline, 'interactions', return_value=rows), \
                     patch.object(history, 'teach_phrase') as teach, self.succeed() as dispatch:
                    result = self.ask('unused', path='/api/native/intents', recording_id='old',
                                      target='office light on', expected_status=400 if blocked else 200)
                if blocked:
                    self.assertEqual(result, {'error': 'Refresh and choose a recording with a transcript.'})
                    teach.assert_not_called()
                else:
                    self.assertEqual(result, {'saved': True})
                    teach.assert_called_once_with('office light on it', 'office light on')
                dispatch.assert_not_called()

    def test_recording_lookup_still_rejects_missing_conflicting_or_discarded_copies(self):
        row = {'id': 'old', 'transcript': 'office light on it', 'status': 'pending'}
        for rows in ([], [row, {**row, 'transcript': 'different'}], [row, {**row, 'status': 'discarded'}]):
            with self.subTest(rows=rows), patch.object(server.voicepipeline, 'interactions', return_value=rows), \
                 patch.object(history, 'teach_phrase') as teach:
                self.ask('unused', path='/api/native/intents', recording_id='old',
                         target='office light on', expected_status=400)
                teach.assert_not_called()

    def test_similarity_rejects_target_direction_and_number_changes(self):
        self.assertTrue(retry_learning.similar('please switch the lights on it', 'turn light on'))
        self.assertTrue(retry_learning.similar('movie timme', 'movie time'))
        self.assertTrue(retry_learning.similar('office light on it', 'turn on the office light'))
        for left, right in [('office light on','kitchen light on'), ('office light on','office light off'),
                            ('set heating to 20','set heating to 21'), ('play rock','play country'),
                            ('open garage','open gate'), ('office light on','study light on')]:
            self.assertFalse(retry_learning.similar(left,right), (left,right))
        self.assertFalse(retry_learning.similar('office on kitchen off', 'office off kitchen on'))
        self.assertFalse(retry_learning.similar('play music then turn light on', 'turn light on then play music'))
