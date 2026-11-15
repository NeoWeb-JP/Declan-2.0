"""Regression tests for explicit voice-recording teaching links."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import history


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
        with sqlite3.connect(self.db) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM learned_intents").fetchone()[0], 1)
        history._initialized.clear()
        self.assertEqual(history.learned_intent("turn lampie on"), "turn lounge lamp on")

    def test_invalid_identifiers_rejected(self):
        for ids in (["invalid/id"], ["x"] * 101, [None]):
            with self.assertRaises(ValueError):
                history.verified_recording_turns(ids)


if __name__ == "__main__":
    unittest.main()
