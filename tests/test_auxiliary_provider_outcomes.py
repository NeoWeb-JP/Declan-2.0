"""Device and media-search providers retain typed outcomes through dispatch."""
import io
import json
import unittest
from contextlib import nullcontext
from dataclasses import FrozenInstanceError, replace
from unittest.mock import Mock, patch

from declan.turn import command_registry
from declan.ha import device_status
import server
from declan.core.execution_results import ExecutionResult, Outcome
from test_command_registry import dependencies
from result_pairs import pair, pair_of


class AuxiliaryProviderOutcomeTests(unittest.TestCase):
    def test_device_core_bypasses_legacy_and_preserves_target(self):
        inventory = [{"entity_id": "light.study", "state": "on", "attributes": {}}]
        with nullcontext():
            result = device_status.describe_result("study", "on", inventory)
        self.assertIs(result.result.outcome, Outcome.CONFIRMED)
        self.assertEqual(result.target, "light.study")
        with self.assertRaises(FrozenInstanceError):
            result.target = "light.other"
        self.assertEqual(pair_of(device_status.describe_result)("study", "on", inventory), pair(result))
        self.assertIs(type(pair(result)[1]), str)

    def test_device_unavailable_and_partial_remain_distinct(self):
        for state, requested, expected in (("unavailable", "down", Outcome.UNAVAILABLE),
                                           ("open", "down", Outcome.PARTIAL)):
            inventory = [{"entity_id": device_status.SCREEN, "state": state, "attributes": {}}]
            result = device_status.describe_result("projector screen", requested, inventory)
            self.assertIs(result.result.outcome, expected)
            self.assertEqual(result.target, device_status.SCREEN)

    def test_device_contract_rejects_unknown_outcomes_and_bad_targets(self):
        for value in (("reply", "invalid", None), ("reply", "confirmed", 42), ("reply",)):
            with self.subTest(value=value), self.assertRaises(ValueError):
                device_status.DeviceStatusResult.coerce(value)

    def test_registry_accepts_typed_device_and_retains_decoration(self):
        deps = dependencies()
        deps.parse_status.return_value = ("study", "on")
        deps.inventory.return_value = ([], None)
        deps.describe_status.return_value = device_status.DeviceStatusResult(
            ExecutionResult("Study is on", Outcome.CONFIRMED), "light.study")
        deps.decorate.side_effect = None
        deps.decorate.return_value = "Study is on. Done."
        result = command_registry.registry(deps).dispatch(command_registry.RequestContext("is study on", "assist"))
        self.assertIs(result.result.outcome, Outcome.CONFIRMED)
        self.assertEqual(result.result.reply, "Study is on. Done.")
        self.assertEqual(result.status_target, "light.study")
        deps.feedback.assert_not_called()

    def test_search_core_dispatches_once_and_keeps_typed_result(self):
        opener = Mock()
        payload = {"service_response": {"response": {"speech": {"plain": {"speech": "Available on TV"}}}}}
        opener.open.return_value = io.BytesIO(json.dumps(payload).encode())
        with patch.object(server.configuration, "get", return_value="conversation.declan_local"), \
             patch.object(server, "ha_device_connection", return_value=("http://ha", {}, opener)), \
             patch.object(server.media_search_agents, "resolve", return_value="conversation.declan_local"):
            expected = server.search_media_result("where can i watch Dune")
        self.assertIs(expected.outcome, Outcome.SEARCH_RESULT)
        opener.open.assert_called_once()
        deps = replace(dependencies(), search_media=Mock(return_value=expected))
        result = command_registry.registry(deps).dispatch(command_registry.RequestContext("where can i watch Dune", "assist"))
        self.assertIs(result.result, expected)
        deps.search_media.assert_called_once()

    def test_search_unmatched_and_unconfigured_contract(self):
        self.assertIsNone(server.search_media_result("hello"))
        with patch.object(server.configuration, "get", return_value=""), \
             patch.object(server, "ha_device_connection", return_value=None):
            result = server.search_media_result("where can i watch Dune")
        self.assertIs(result.outcome, Outcome.NOT_CONFIGURED)


if __name__ == "__main__":
    unittest.main()
