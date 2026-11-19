"""Provider outcomes stay typed until explicit public compatibility adapters."""
import io
import json
import unittest
from unittest.mock import Mock, patch

from declan.turn import command_registry
from declan.turn.active_routine_registry import ActiveRoutineRegistry
import server
from declan.ha import script_discovery
from declan.core.execution_results import ExecutionResult, Outcome


class ProviderDispatchOutcomeTests(unittest.TestCase):
    def test_script_entrypoints_preserve_typed_identity_without_legacy_calls(self):
        expected = ExecutionResult("Requested", Outcome.STARTED)
        with patch.object(script_discovery, "enqueue", side_effect=AssertionError("legacy receipt")), \
             patch.object(script_discovery, "execute", side_effect=AssertionError("legacy execution")), \
             patch.object(script_discovery, "_enqueue_provider", return_value=(expected, "receipt")), \
             patch.object(script_discovery, "_execute_provider", return_value=(expected, "trace")):
            queued, receipt = script_discovery.enqueue_result(None, "script.tea", {})
            executed, trace = script_discovery.execute_result(None, {"entity_id": "script.tea"})
        self.assertIs(queued, expected)
        self.assertIs(executed, expected)
        self.assertEqual((receipt, trace), ("receipt", "trace"))

    def test_lighting_registry_preserves_typed_result_identity(self):
        expected = ExecutionResult("Cannot verify", Outcome.UNVERIFIED)
        handler = Mock(return_value=expected)
        registry = command_registry.lighting_registry(
            matches=lambda *_: True, parse_light_command=Mock(),
            handle_light_request=handler, action_results=[], last_lights=(),
            origin_device="kitchen")
        result = registry.dispatch(command_registry.RequestContext("lights on", "assist"))
        self.assertIs(result.result, expected)
        handler.assert_called_once()

    def test_typed_lighting_dispatch_bypasses_legacy_apis(self):
        expected = ExecutionResult("Done", Outcome.CONFIRMED)
        with patch.object(server, "set_lights", side_effect=AssertionError("legacy executor")), \
             patch.object(server, "handle_light_request", side_effect=AssertionError("legacy intent")), \
             patch.object(server, "set_lights_result", return_value=expected) as execute:
            self.assertIs(server.handle_light_request_result("turn on kitchen lights"), expected)
        execute.assert_called_once()

    def test_lighting_read_only_status_and_legacy_strings(self):
        inventory = [{"entity_id": "light.kitchen", "state": "on", "attributes": {}}]
        with patch.object(server, "ha_device_connection", return_value=("http://ha", {}, Mock())), \
             patch.object(server, 'read_ha_inventory_result', return_value=(inventory, None)), \
             patch.object(server, "add_sass", side_effect=lambda reply, *_: reply):
            typed = server.set_lights_result("", None)
            legacy = server.set_lights("", None)
        self.assertIs(typed.outcome, Outcome.CONFIRMED)
        self.assertEqual(legacy, typed.as_legacy_pair())
        self.assertIs(type(legacy[1]), str)

    def test_lighting_inventory_error_is_validated(self):
        with patch.object(server, "ha_device_connection", return_value=("http://ha", {}, Mock())), \
             patch.object(server, 'read_ha_inventory_result', return_value=([], "invalid")):
            with self.assertRaises(ValueError):
                server.set_lights_result("kitchen", "on")

    def test_routine_selection_failures_bypass_legacy_execution(self):
        for selection, outcome in (("auto_ambiguous", Outcome.UNRESOLVED),
                                   ("unconfigured_house_status", Outcome.NOT_CONFIGURED),
                                   ("missing", Outcome.NOT_CONFIGURED)):
            with self.subTest(selection=selection):
                result, status = server.execute_routine_result((selection, {}), [])
            self.assertIs(result.outcome, outcome)
            self.assertIsNone(status)

    def test_cancellation_requests_once_and_remains_unverified(self):
        opener = Mock()
        opener.open.return_value = io.BytesIO(b"[]")
        with patch.object(server, "ha_device_connection", return_value=("http://ha", {}, opener)), \
             patch.object(server, "ACTIVE_ROUTINE_REGISTRY", ActiveRoutineRegistry()):
            with server.track_routine("tea", "script.make_tea"):
                result, status = server.stop_pending_routines_result()
        self.assertIs(result.outcome, Outcome.UNVERIFIED)
        self.assertIsNone(status)
        opener.open.assert_called_once()
        self.assertEqual(json.loads(opener.open.call_args.args[0].data), {"entity_id": "script.make_tea"})

    def test_cancellation_result_carries_typed_outcome(self):
        with patch.object(server, "stop_pending_routines_result", return_value=(
                ExecutionResult("None active", Outcome.CONFIRMED), None)):
            result, status = server.stop_pending_routines_result()
        self.assertEqual((result.reply, result.outcome.value, status), ("None active", "confirmed", None))


if __name__ == "__main__":
    unittest.main()
