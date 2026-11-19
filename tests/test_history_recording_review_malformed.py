"""History regression tests executed by unittest discovery."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import json
from time import time

import history


class HistoryRegressionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.old_database = history.DATABASE
        self.addCleanup(setattr, history, "DATABASE", self.old_database)
        history.DATABASE = Path(self.directory.name) / "history.sqlite3"

    def test_recording_review_ignores_unhashable_stored_identifiers(self):
        history.DATABASE = Path(self.directory.name) / "history.sqlite3"
        with history.database() as connection:
            for index, identifier in enumerate((["bad"], {"nested": "bad"}, "valid-id")):
                connection.execute(
                    "INSERT INTO turns(created_at, session_id, source, message, reply, speaker_match) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (time(), f"session-{index}", "assist", "hello", "hi",
                     json.dumps({"interaction_id": identifier})),
                )
        assert history.verified_recording_turns(["valid-id"]) == {"valid-id": 3}


    def test_recording_review_rejects_ambiguous_valid_ids(self):
        history.DATABASE = Path(self.directory.name) / "history.sqlite3"
        with history.database() as connection:
            for index in range(2):
                connection.execute(
                    "INSERT INTO turns(created_at, session_id, source, message, reply, speaker_match) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (time(), f"session-{index}", "assist", "hello", "hi",
                     json.dumps({"interaction_id": "duplicate"})),
                )
        assert history.verified_recording_turns(["duplicate"]) == {}

