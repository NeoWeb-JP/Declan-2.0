"""Regression tests for malformed persisted recording review metadata."""

import json
from time import time

import history


def test_recording_review_ignores_unhashable_stored_identifiers(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "DATABASE", tmp_path / "history.sqlite3")
    with history.database() as connection:
        for index, identifier in enumerate((["bad"], {"nested": "bad"}, "valid-id")):
            connection.execute(
                "INSERT INTO turns(created_at, session_id, source, message, reply, speaker_match) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (time(), f"session-{index}", "assist", "hello", "hi",
                 json.dumps({"interaction_id": identifier})),
            )
    assert history.verified_recording_turns(["valid-id"]) == {"valid-id": 3}


def test_recording_review_rejects_ambiguous_valid_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "DATABASE", tmp_path / "history.sqlite3")
    with history.database() as connection:
        for index in range(2):
            connection.execute(
                "INSERT INTO turns(created_at, session_id, source, message, reply, speaker_match) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (time(), f"session-{index}", "assist", "hello", "hi",
                 json.dumps({"interaction_id": "duplicate"})),
            )
    assert history.verified_recording_turns(["duplicate"]) == {}
