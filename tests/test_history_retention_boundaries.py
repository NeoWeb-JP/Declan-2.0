"""History regression tests executed by unittest discovery."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import json

import history


class HistoryRegressionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.old_database = history.DATABASE
        self.addCleanup(setattr, history, "DATABASE", self.old_database)
        history.DATABASE = Path(self.directory.name) / "history.sqlite3"

    def test_recording_links_respect_shorter_history_retention(self):
        history.DATABASE = Path(self.directory.name) / "history.sqlite3"
        self.env_patch = patch.dict(os.environ, {"DECLAN_HISTORY_RETENTION_DAYS": "1"})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.time_patch = patch.object(history, "time", return_value=2_000_000.0)
        self.time_patch.start()
        self.addCleanup(self.time_patch.stop)
        with history.database() as connection:
            for age, name in ((2 * 86400, "expired"), (3600, "recent")):
                connection.execute(
                    "INSERT INTO turns(created_at, session_id, source, message, reply, speaker_match) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (2_000_000.0 - age, name, "assist", "hello", "hi",
                     json.dumps({"interaction_id": name})),
                )
        assert history.verified_recording_turns(["expired", "recent"]) == {"recent": 2}


    def test_teaching_from_expired_history_is_rejected(self):
        history.DATABASE = Path(self.directory.name) / "history.sqlite3"
        self.env_patch = patch.dict(os.environ, {"DECLAN_HISTORY_RETENTION_DAYS": "1"})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.time_patch = patch.object(history, "time", return_value=2_000_000.0)
        self.time_patch.start()
        self.addCleanup(self.time_patch.stop)
        with history.database() as connection:
            expired = connection.execute(
                "INSERT INTO turns(created_at, session_id, source, message, reply) "
                "VALUES (?, ?, ?, ?, ?)",
                (2_000_000.0 - 2 * 86400, "expired", "assist", "turn lights", "sorry"),
            ).lastrowid
            recent = connection.execute(
                "INSERT INTO turns(created_at, session_id, source, message, reply) "
                "VALUES (?, ?, ?, ?, ?)",
                (2_000_000.0 - 60, "recent", "assist", "turn lights", "sorry"),
            ).lastrowid
        try:
            history.teach_intent(expired, "turn on lights", "sorry")
        except ValueError as error:
            assert "Choose a command from history" in str(error)
        else:
            raise AssertionError("Expired turn must not be eligible for training")
        history.teach_intent(recent, "turn on lights", "sorry")
        assert history.learned_intent("turn lights") == "turn on lights"

