"""Typed action evidence crosses response/history boundaries as plain JSON."""
from lighting_action_evidence import LightingActionStatus
from routine_action_evidence import RoutineActionStatus
from typing import Any, cast
import io
import json
import sqlite3
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import Mock, patch

from action_evidence_wire import action_evidence_to_wire
from execution_results import ActionResult, ActionStatus, ExecutionResult, MovieLaunchResult, MovieLaunchStatus, Outcome
from lighting_action_evidence import LightingActionEvidence
from movie_action_evidence import MovieActionEvidence
from routine_action_evidence import RoutineActionEvidence
import conversation_persistence
import history
import server


class ActionEvidencePersistenceTests(unittest.TestCase):
    def rows(self):
        return [ActionResult(0, "light.study", "light.turn_on", ActionStatus.CONFIRMED),
                LightingActionEvidence("Study", "turn_on", LightingActionStatus.PLANNED, "light.study"),
                RoutineActionEvidence("Music", RoutineActionStatus.REQUESTED, required=False),
                MovieActionEvidence("TV", MovieLaunchStatus.SENT, "remote.tv", "Accepted"),
                {"target": "legacy", "status": "custom_legacy", "extra": [1, True]}]

    def test_mixed_typed_rows_serialize_without_losing_legacy_fields(self):
        rows = self.rows()
        wire = action_evidence_to_wire(tuple(rows))
        self.assertEqual(wire, [row.to_wire() for row in rows[:4]] + [rows[4]])
        self.assertIs(wire[-1], rows[-1])
        self.assertTrue(all(type(row["status"]) is str for row in wire))
        self.assertEqual(json.loads(json.dumps(wire)), wire)
        self.assertIsInstance(rows[1], LightingActionEvidence)

    def test_legacy_only_values_keep_identity_and_json_compatibility(self):
        for rows in (None, [], [{"status": "sent", "extra": "preserve"}], ["legacy", 1], {"legacy": "value"}):
            self.assertIs(action_evidence_to_wire(rows), rows)

    def test_direct_history_record_persists_mixed_typed_rows(self):
        rows = self.rows()
        with tempfile.TemporaryDirectory() as directory, patch.object(history, "DATABASE", Path(directory) / "history.sqlite3"):
            identifier = history.record("session", "chat", "lights", "Done", "confirmed", action_results=rows)
            turn = next(turn for turn in history.recent() if turn["id"] == identifier)
        self.assertEqual(turn["action_results"], action_evidence_to_wire(rows))
        self.assertEqual(turn["action_results"][3]["status"], "sent")

    def save(self, rows, record):
        reply = {"session_id": "session", "reply": "Done"}
        saved = conversation_persistence.save_turn(
            reply, source="assist", message="lights", outcome=Outcome.CONFIRMED,
            routine_status=None, action_results=rows, phrase_suggestion=None, speaker=None,
            record=record, diagnostic_id=lambda: "trace", log_error=Mock())
        return reply, saved

    def test_response_and_history_callback_share_wire_rows_and_record_once(self):
        rows = self.rows()
        record = Mock()
        reply, saved = self.save(rows, record)
        self.assertTrue(saved)
        record.assert_called_once()
        self.assertIs(reply["action_results"], record.call_args.args[6])
        self.assertEqual(reply["action_results"], action_evidence_to_wire(rows))
        self.assertIsInstance(rows[2], RoutineActionEvidence)

    def test_history_failure_remains_nonfatal_without_action_response(self):
        record = Mock(side_effect=sqlite3.OperationalError("locked"))
        reply, saved = self.save(self.rows(), record)
        self.assertFalse(saved)
        self.assertFalse(reply["history_saved"])
        self.assertNotIn("action_results", reply)
        record.assert_called_once()

    def test_movie_evidence_is_frozen_and_cannot_claim_confirmed_completion(self):
        evidence = MovieActionEvidence("TV", MovieLaunchStatus.SENT, "remote.tv", "Accepted")
        self.assertEqual(evidence.to_wire()["status"], "sent")
        with self.assertRaises(FrozenInstanceError):
            setattr(evidence, 'status', MovieLaunchStatus.FAILED)
        with self.assertRaises(ValueError):
            cast(Any, MovieActionEvidence)("TV", "confirmed", "remote.tv", "Accepted")

    def test_movie_provider_emits_sent_or_skipped_evidence_without_repeated_dispatch(self):
        for outcome, expected in ((Outcome.REPORTED_SUCCESS, MovieLaunchStatus.SENT),
                                   (Outcome.UNVERIFIED, MovieLaunchStatus.SKIPPED)):
            opener = Mock()
            opener.open.return_value = io.BytesIO(b'{"service_response":{}}')
            mapping = {"movie": {"script": "script.movie", "remote": "remote.tv", "fields": {}, "sensitive": False}}
            actions: list[dict[str, Any]]
            actions = []
            with patch.object(server, "ha_device_connection", return_value=("http://ha", {}, opener)), \
                 patch.object(server.routine_registry, "load", return_value=mapping), \
                 patch.object(server, "ROUTINE_COOLDOWN", server.routine_cooldown.RoutineCooldown()), patch.object(server, "sleep"), \
                 patch.object(server, "routine_completion_result", return_value=(ExecutionResult("Routine", outcome), None)), \
                 patch.object(server, "launch_movie_app_result", return_value=MovieLaunchResult(MovieLaunchStatus.SENT, "Accepted")) as launch, \
                 patch.object(server, "MovieActionEvidence", wraps=MovieActionEvidence) as model:
                server.run_routine_result("movie", movie_action="start", movie_app=("TV", "tv"), action_results=actions)
            self.assertIs(model.call_args.args[1], expected)
            self.assertEqual(actions[-1]["status"], expected.value)
            self.assertIs(type(actions[-1]["status"]), str)
            self.assertEqual(launch.call_count, 1 if outcome is Outcome.REPORTED_SUCCESS else 0)
            opener.open.assert_called_once()


if __name__ == "__main__":
    unittest.main()
