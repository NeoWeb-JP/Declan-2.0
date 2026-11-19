"""Regression tests for bedroom routine dispatch extraction."""
import unittest
from unittest.mock import patch, Mock

import server
from declan.turn import bedroom_routine_dispatch as dispatch
from declan.core.execution_results import Outcome


class BedroomRoutineExtractionTests(unittest.TestCase):
    def test_wrapper_preserves_server_patch_points(self):
        with patch.object(dispatch, "run_sexy_time_result", return_value="sentinel") as extracted:
            self.assertEqual(server.run_sexy_time_result("start", None), "sentinel")
        kwargs = extracted.call_args.kwargs
        self.assertIs(kwargs["registry"], server.routine_registry)
        self.assertIs(kwargs["gates"], server.ROUTINE_EXECUTION_GATES)
        self.assertIs(kwargs["inventory_reader"], server.read_music_inventory_result)
        self.assertIs(kwargs["inventory_module"], server.ha_inventory)
        self.assertIs(kwargs["music_provider"], server.music)
        self.assertIs(kwargs["request_factory"], server.Request)
        self.assertIs(kwargs["token_hex"], server.secrets.token_hex)
        self.assertIs(kwargs["choose_response"], server.choose_line)
        self.assertIs(kwargs["guest_mode"], server.read_guest_mode)

    def test_unconfigured_ha_is_not_configured(self):
        result, detail = server.run_sexy_time_result("start", None)
        self.assertEqual(result.outcome, Outcome.NOT_CONFIGURED)
        self.assertIsNone(detail)

    def test_unmapped_routine_is_not_configured(self):
        with patch.object(server.routine_registry, "load", return_value={}):
            result, detail = server.run_sexy_time_result("start", ("http://ha", {}, Mock()))
        self.assertEqual(result.outcome, Outcome.NOT_CONFIGURED)
        self.assertIsNone(detail)

    def test_sensitive_routine_requires_confirmation_before_dispatch(self):
        with patch.object(server.routine_registry, "load", return_value={
            "sexy_time": {"sensitive": True, "script": "script.sexy_time"}
        }):
            result, detail = server.run_sexy_time_result("start", ("http://ha", {}, Mock()))
        self.assertEqual(result.outcome, Outcome.UNRESOLVED)
        self.assertIsNone(detail)


if __name__ == "__main__":
    unittest.main()
