"""Regression tests for extracted stop-all and origin music actions."""
import unittest
from unittest.mock import patch

import server
from declan.music import music_stop_dispatch as dispatch
from execution_results import Outcome


class MusicStopExtractionTests(unittest.TestCase):
    def test_stop_all_wrapper_preserves_runtime_patch_points(self):
        with patch.object(dispatch, "stop_everywhere_result", return_value="sentinel") as extracted:
            self.assertEqual(server._stop_everywhere_typed_core(None), "sentinel")
        kwargs = extracted.call_args.kwargs
        self.assertIs(kwargs["inventory_reader"], server.read_music_inventory_result)
        self.assertIs(kwargs["inventory_module"], server.ha_inventory)
        self.assertIs(kwargs["music_provider"], server.music)

    def test_origin_wrapper_preserves_runtime_patch_points(self):
        with patch.object(dispatch, "stop_origin_result", return_value="sentinel") as extracted:
            self.assertEqual(server.stop_origin_result(None, "satellite", "device"), "sentinel")
        kwargs = extracted.call_args.kwargs
        self.assertIs(kwargs["inventory_reader"], server.read_music_inventory_result)
        self.assertIs(kwargs["inventory_module"], server.ha_inventory)
        self.assertIs(kwargs["music_provider"], server.music)
        self.assertIs(kwargs["timer_provider"], server.timers)

    def test_stop_all_without_connection_is_not_configured(self):
        result, status = server.stop_everywhere_result(None)
        self.assertEqual(result.outcome, Outcome.NOT_CONFIGURED)
        self.assertIn("Home Assistant", status)

    def test_stop_origin_without_identity_is_unresolved(self):
        result, status = server.stop_origin_result(None, None, None)
        self.assertEqual(result.outcome, Outcome.UNRESOLVED)
        self.assertIn("satellite", status)

    def test_legacy_stop_all_triple_stays_compatible(self):
        reply, outcome, status = server.stop_everywhere_output(None)
        self.assertEqual(reply, "")
        self.assertEqual(outcome, Outcome.NOT_CONFIGURED.value)
        self.assertIsInstance(status, str)


if __name__ == "__main__":
    unittest.main()
