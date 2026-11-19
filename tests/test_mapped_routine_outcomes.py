"""Typed mapped routine execution preserves evidence and legacy contracts."""
from email.message import Message
import io
import json
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

import server
from declan.core.execution_results import ExecutionResult, Outcome


class MappedRoutineOutcomeTests(unittest.TestCase):
    def test_custom_routine_validates_correlated_required_step_evidence(self):
        for remote, steps, expected in (
                ("success", [{"target": "light", "status": "confirmed"}], Outcome.REPORTED_SUCCESS),
                ("success", [{"target": "light", "status": "unverified"}], Outcome.UNVERIFIED),
                ("unknown", [], Outcome.UNVERIFIED),
                ("partial", [], Outcome.PARTIAL)):
            with self.subTest(remote=remote, steps=steps):
                opener = Mock()
                def respond(request, timeout):
                    payload = json.loads(request.data)
                    return io.BytesIO(json.dumps({"service_response": {
                        **payload, "outcome": remote, "steps": steps,
                    }}).encode())
                opener.open.side_effect = respond
                mapping = {"tea": {"script": "script.tea", "fields": {}}}
                with patch.object(server.routine_registry, "load", return_value=mapping), \
                     patch.object(server, "ha_device_connection", return_value=("http://ha", {}, opener)), \
                     patch.object(server, "run_custom_routine", side_effect=AssertionError("legacy wrapper")):
                    result, detail = server.run_custom_routine_result("tea")
                self.assertIs(result.outcome, expected)
                self.assertIsNone(detail)
                opener.open.assert_called_once()

    def test_mapped_execution_consumes_typed_completion_without_legacy_formatter(self):
        opener = Mock()
        opener.open.return_value = io.BytesIO(b'{"service_response":{"schema_version":1}}')
        expected = ExecutionResult("Routine finished", Outcome.REPORTED_SUCCESS)
        mapping = {"morning": {"script": "script.morning", "fields": {}, "sensitive": False}}
        with patch.object(server.routine_registry, "load", return_value=mapping), \
             patch.object(server, "ha_device_connection", return_value=("http://ha", {}, opener)), \
             patch.object(server, "ROUTINE_COOLDOWN", server.routine_cooldown.RoutineCooldown()), \
             patch.object(server, "format_routine_result", side_effect=AssertionError("legacy formatter")), \
             patch.object(server, "routine_completion_result", return_value=(expected, "evidence")) as complete:
            result, detail = server.run_routine_result("morning")
        self.assertIs(result, expected)
        self.assertEqual(detail, "evidence")
        complete.assert_called_once()
        opener.open.assert_called_once()

    def test_rejected_request_is_not_retried_and_lock_is_released(self):
        opener = Mock()
        opener.open.side_effect = HTTPError("http://ha", 403, "denied", Message(), io.BytesIO())
        mapping = {"morning": {"script": "script.morning", "fields": {}, "sensitive": False}}
        with patch.object(server.routine_registry, "load", return_value=mapping), \
             patch.object(server, "ha_device_connection", return_value=("http://ha", {}, opener)), \
             patch.object(server, "ROUTINE_COOLDOWN", server.routine_cooldown.RoutineCooldown()):
            result, _ = server.run_routine_result("morning")
        self.assertIs(result.outcome, Outcome.REJECTED)
        opener.open.assert_called_once()
        self.assertFalse(server.ROUTINE_EXECUTION_GATES.for_routine("morning").locked())

    def test_bedroom_stop_uses_typed_music_without_legacy_roundtrip(self):
        opener = Mock()
        def respond(request, timeout):
            body = json.loads(request.data)
            return io.BytesIO(json.dumps({"service_response": {**body, "lighting_ok": True}}).encode())
        opener.open.side_effect = respond
        mapping = {"sexy_time": {"script": "script.bedroom", "sensitive": False}}
        with patch.object(server.routine_registry, "load", return_value=mapping), \
             patch.object(server, 'read_music_inventory_result', return_value=([], None)), \
             patch.object(server.music, "music_players", return_value=({"bedroom": "media_player.bedroom"}, {})), \
             patch.object(server.music, "control", side_effect=AssertionError("legacy music")), \
             patch.object(server.music, "control_result", return_value=ExecutionResult("Cannot verify", Outcome.UNVERIFIED)) as stop, \
             patch.object(server, "read_guest_mode", return_value="off"):
            result, detail = server.run_sexy_time_result("end", ("http://ha", {}, opener))
        self.assertIs(result.outcome, Outcome.PARTIAL)
        self.assertIn("could not be verified", detail)
        stop.assert_called_once()
        opener.open.assert_called_once()

    def test_legacy_routine_adapters_preserve_plain_strings_and_detail(self):
        expected = ExecutionResult("Routine finished", Outcome.REPORTED_SUCCESS)
        for legacy, typed, arguments in (
                (server.run_custom_routine, "run_custom_routine_result", ("tea",)),
                (server.run_routine, "run_routine_result", ("morning",)),
                (server.format_routine_result, "routine_completion_result", ({}, "request", "script.tea", "morning", None, []))):
            with self.subTest(provider=typed), patch.object(server, typed, return_value=(expected, "evidence")):
                result = legacy(*arguments)
            self.assertEqual(result, ("Routine finished", "reported_success", "evidence"))
            self.assertIs(type(result[1]), str)

    def test_chained_outcomes_validate_inputs_and_preserve_legacy_type(self):
        self.assertIs(server.chained_outcome_result("execution_completed", "confirmed"), Outcome.EXECUTION_COMPLETED)
        self.assertIs(type(server.chained_outcome("execution_completed", "confirmed")), str)
        with self.assertRaises(ValueError):
            server.chained_outcome_result("invalid", "confirmed")


if __name__ == "__main__":
    unittest.main()
