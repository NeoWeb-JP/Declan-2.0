"""Regression tests for explicit voice-recording teaching links."""
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import history
import server


class VerifiedRecordingLinksTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "history.sqlite3"
        self.patch = patch.object(history, "DATABASE", self.db)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_unique_link_only_and_no_transcript_guessing(self):
        history.record("s", "assist", "Turn kitchen on", "Done", speaker={
            "interaction_id": "recording_1", "name": "Jaco", "confidence": 0.9
        })
        history.record("s", "assist", "Turn kitchen on", "Done", speaker={
            "interaction_id": "recording_2", "name": "Jaco", "confidence": 0.9
        })
        history.record("s", "browser_keyboard", "Turn kitchen on", "Done")
        links = history.verified_recording_turns(["recording_1", "recording_2", "missing"])
        self.assertEqual(set(links), {"recording_1", "recording_2"})
        self.assertNotEqual(links["recording_1"], links["recording_2"])

    def test_duplicate_link_is_ambiguous(self):
        for _ in range(2):
            history.record("s", "assist", "Turn lights on", "Done", speaker={
                "interaction_id": "duplicate", "name": "Edd", "confidence": 0.9
            })
        self.assertEqual(history.verified_recording_turns(["duplicate"]), {})

    def test_explicit_teaching_persists_without_automatic_learning(self):
        history.record("s", "assist", "Turn lampie on", "Unrecognised", speaker={
            "interaction_id": "clip1", "name": "Jaco", "confidence": 0.9
        })
        self.assertEqual(history.learned_intents(), {})
        turn_id = history.verified_recording_turns(["clip1"])["clip1"]
        history.teach_intent(turn_id, "turn lounge lamp on", "Unrecognised")
        self.assertEqual(history.learned_intent("turn lampie on"), "turn lounge lamp on")
        with history.database() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM learned_intents").fetchone()[0], 1)
        history._initialized.clear()
        self.assertEqual(history.learned_intent("turn lampie on"), "turn lounge lamp on")

    def test_invalid_identifiers_rejected(self):
        for ids in (["invalid/id"], ["x"] * 101, [None]):
            with self.assertRaises(ValueError):
                history.verified_recording_turns(ids)

    def remote_get(self, path, supplied='x' * 32):
        handler = object.__new__(server.Handler)
        handler.path = path
        handler.client_address = ('192.0.2.10', 12345)
        handler.server = SimpleNamespace(server_port=52737)
        handler.headers = Message()
        handler.headers['Authorization'] = 'Bearer ' + supplied
        handler.headers['Host'] = 'declan.internal:52737'
        handler.has_ingress_access = lambda: False
        handler.send_json = Mock()
        handler.send_body = Mock()
        with patch.dict(server.os.environ, {'DECLAN_ASSIST_TOKEN':'x' * 32}):
            handler.do_GET()
        return handler.send_json.call_args.args

    def test_ha_token_from_remote_host_loads_link_and_actual_reply(self):
        history.record('s','assist','study light on it',server.UNMATCHED_REPLY,
                       speaker={'interaction_id':'clip','name':'Jaco','confidence':0.49})
        status, payload = self.remote_get('/api/history/recording-links?ids=clip')
        self.assertEqual(status,200,payload)
        turn_id=payload['links']['clip']
        self.assertEqual(payload['turns'][str(turn_id)]['reply'],server.UNMATCHED_REPLY)
        self.assertEqual(payload['turns'][str(turn_id)]['message'],'study light on it')

    def test_recording_links_still_require_valid_token_and_valid_ids(self):
        self.assertEqual(self.remote_get('/api/history/recording-links?ids=clip', supplied='wrong')[0],403)
        self.assertEqual(self.remote_get('/api/history/recording-links?ids=invalid/id')[0],400)

    def test_read_token_does_not_authorize_other_history_routes(self):
        for path in ('/api/history/export','/api/history/clear','/api/history/intents',
                     '/api/history/recording-links/extra?ids=clip'):
            with self.subTest(path=path):
                self.assertEqual(self.remote_get(path)[0],403)


if __name__ == "__main__":
    unittest.main()
