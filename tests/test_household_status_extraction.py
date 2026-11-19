"""Regression tests for HA status and legacy routine extraction."""
import unittest
from unittest.mock import patch

import server
from declan.ha import ha_household_status as status_module
import routine_execution_dispatch as routine_module
from execution_results import Outcome
from declan.ha.home_assistant_results import HomeAssistantStatus


class HouseholdStatusExtractionTests(unittest.TestCase):
    def test_status_wrapper_uses_live_server_dependencies(self):
        with patch.object(status_module, "home_assistant_status_result", return_value="sentinel") as helper:
            self.assertEqual(server.home_assistant_status_result(), "sentinel")
        self.assertIs(helper.call_args.kwargs["history_store"], server.history)
        self.assertIs(helper.call_args.kwargs["request_factory"], server.Request)
        self.assertIs(helper.call_args.kwargs["opener_factory"], server.build_opener)

    def test_guest_and_visitors_wrappers_are_patchable(self):
        with patch.object(status_module, "read_guest_mode", return_value="guest") as helper:
            self.assertEqual(server.read_guest_mode(), "guest")
        self.assertIs(helper.call_args.kwargs["entities"], server.household_entities)
        with patch.object(status_module, "read_visitors_present", return_value=True) as helper:
            self.assertTrue(server.read_visitors_present())
        self.assertIs(helper.call_args.kwargs["config"], server.configuration)

    def test_missing_ha_credentials_are_not_configured(self):
        with patch.dict(server.os.environ, {"DECLAN_HA_URL": "", "DECLAN_HA_TOKEN": ""}):
            with patch.object(server.history, "has_recent_assist", return_value=False):
                result = server.home_assistant_status_result()
        self.assertEqual(result.status, HomeAssistantStatus.NOT_CONFIGURED)

    def test_missing_visitor_credentials_return_unknown(self):
        with patch.dict(server.os.environ, {"DECLAN_HA_URL": "", "DECLAN_HA_TOKEN": ""}):
            self.assertIsNone(server.read_visitors_present())

    def test_custom_routine_wrapper_preserves_dependencies(self):
        with patch.object(routine_module, "run_custom_routine_result", return_value="sentinel") as helper:
            self.assertEqual(server.run_custom_routine_result("morning"), "sentinel")
        self.assertIs(helper.call_args.kwargs["registry"], server.routine_registry)
        self.assertIs(helper.call_args.kwargs["connect"], server.ha_device_connection)
        self.assertIs(helper.call_args.kwargs["areas_reader"], server.read_ha_areas)
        self.assertIs(helper.call_args.kwargs["parse_steps"], server.routine_action_results_typed)

    def test_custom_routine_unconfigured_returns_safe_outcome(self):
        with patch.object(server.routine_registry, "load", return_value={}):
            result, detail = server.run_custom_routine_result("nonexistent")
        self.assertEqual(result.outcome, Outcome.NOT_CONFIGURED)
        self.assertIsNone(detail)


if __name__ == "__main__":
    unittest.main()
