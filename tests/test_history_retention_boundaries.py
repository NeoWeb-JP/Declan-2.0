"""History retention applies consistently before hourly pruning."""

import json

import pytest

import history


def test_recording_links_respect_shorter_history_retention(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "DATABASE", tmp_path / "history.sqlite3")
    monkeypatch.setenv("DECLAN_HISTORY_RETENTION_DAYS", "1")
    monkeypatch.setattr(history, "time", lambda: 2_000_000.0)
    with history.database() as connection:
        for age, name in ((2 * 86400, "expired"), (3600, "recent")):
            connection.execute(
                "INSERT INTO turns(created_at, session_id, source, message, reply, speaker_match) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (2_000_000.0 - age, name, "assist", "hello", "hi",
                 json.dumps({"interaction_id": name})),
            )
    assert history.verified_recording_turns(["expired", "recent"]) == {"recent": 2}


def test_teaching_from_expired_history_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "DATABASE", tmp_path / "history.sqlite3")
    monkeypatch.setenv("DECLAN_HISTORY_RETENTION_DAYS", "1")
    monkeypatch.setattr(history, "time", lambda: 2_000_000.0)
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
    with pytest.raises(ValueError, match="Choose a command from history"):
        history.teach_intent(expired, "turn on lights", "sorry")
    history.teach_intent(recent, "turn on lights", "sorry")
    assert history.learned_intent("turn lights") == "turn on lights"
