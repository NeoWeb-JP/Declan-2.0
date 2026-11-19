"""Regression coverage for extracted lighting execution and server patch seams."""
import unittest
from unittest.mock import patch

import server
from declan.ha import lighting_execution_dispatch as dispatch
from execution_results import Outcome


class LightingExecutionExtractionTests(unittest.TestCase):
    def test_wrapper_preserves_runtime_dependencies(self):
        with patch.object(dispatch, "set_lights_result", return_value="sentinel") as helper:
            self.assertEqual(server.set_lights_result("kitchen", "on"), "sentinel")
        kwargs = helper.call_args.kwargs
        self.assertIs(kwargs["connect"], server.ha_device_connection)
        self.assertIs(kwargs["inventory_reader"], server.read_ha_inventory_result)
        self.assertIs(kwargs["areas_reader"], server.read_ha_areas)
        self.assertIs(kwargs["switch_dispatch"], server.set_switch_as_light_result)
        self.assertIs(kwargs["sass"], server.add_sass)
        self.assertIs(kwargs["evidence_factory"], server.LightingActionEvidence)
        self.assertIs(kwargs["request_factory"], server.Request)
        self.assertIs(kwargs["clock"], server.monotonic)
        self.assertIs(kwargs["sleeper"], server.sleep)

    def test_missing_ha_returns_not_configured(self):
        with patch.object(server, "ha_device_connection", return_value=None):
            result = server.set_lights_result("kitchen", "on")
        self.assertEqual(result.outcome, Outcome.NOT_CONFIGURED)

    def test_legacy_api_preserves_result_pair(self):
        with patch.object(server, "set_lights_result") as result:
            result.return_value.as_legacy_pair.return_value = ("reply", "confirmed")
            self.assertEqual(server.set_lights("kitchen", "off"), ("reply", "confirmed"))

    def test_unavailable_inventory_does_not_dispatch(self):
        with patch.object(server, "ha_device_connection", return_value=("http://ha", {}, None)):
            with patch.object(server, "read_ha_inventory_result", return_value=(None, Outcome.UNAVAILABLE)):
                result = server.set_lights_result("kitchen", "on")
        self.assertEqual(result.outcome, Outcome.UNAVAILABLE)


if __name__ == "__main__":
    unittest.main()
