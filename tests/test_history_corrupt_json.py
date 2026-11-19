"""History reads survive malformed and wrong-shaped legacy JSON."""

import json
from time import time

import history


def test_recent_history_skips_invalid_json_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "DATABASE", tmp_path / "history.sqlite3")
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


def test_recent_history_keeps_normal_empty_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "DATABASE", tmp_path / "history.sqlite3")
    history.record("session", "assist", "hello", "hi")
    row = history.recent()[0]
    assert row["action_results"] == []
    assert row["speaker_match"] is None
