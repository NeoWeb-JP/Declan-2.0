"""History regression tests executed by unittest discovery."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from time import time

import history


class HistoryRegressionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.old_database = history.DATABASE
        self.addCleanup(setattr, history, "DATABASE", self.old_database)
        history.DATABASE = Path(self.directory.name) / "history.sqlite3"

    def test_recent_history_skips_invalid_json_fields(self):
        history.DATABASE = Path(self.directory.name) / "history.sqlite3"
        cases = (
            ("{broken", "[", [], None),
            ('{"not": "actions"}', "[]", [], None),
            ('[{"status": "ok"}]', '{"name": "Example"}',
             [{"status": "ok"}], {"name": "Example"}),
            ("null", "42", [], None),
        )
        with history.database() as connection:
            for index, (actions, speaker, _, __) in enumerate(cases):
                connection.execute(
                    "INSERT INTO turns(created_at, session_id, source, message, reply, "
                    "action_results, speaker_match) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (time(), str(index), "assist", "hello", "hi", actions, speaker),
                )
        actual = list(reversed(history.recent()))
        assert len(actual) == len(cases)
        for row, (_, __, actions, speaker) in zip(actual, cases):
            assert row["action_results"] == actions
            assert row["speaker_match"] == speaker


    def test_recent_history_keeps_normal_empty_fields(self):
        history.DATABASE = Path(self.directory.name) / "history.sqlite3"
        history.record("session", "assist", "hello", "hi")
        row = history.recent()[0]
        assert row["action_results"] == []
        assert row["speaker_match"] is None

