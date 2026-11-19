"""Light and inventory turns record per-stage timings so latency can be measured."""
import os
import unittest
from unittest.mock import patch

import diagnostics
import ha_inventory
import server
import test_home_assistant as fixtures
from execution_results import Outcome


class RecordHelperTests(unittest.TestCase):
    def test_record_appends_completed_stage_with_fields_and_duration(self):
        trace = {"stages": []}
        token = diagnostics.ACTIVE.set(trace)
        self.addCleanup(diagnostics.ACTIVE.reset, token)
        with patch.object(diagnostics, "monotonic", return_value=12.5):
            diagnostics.record("demo", 12.0, lights=2)
        (entry,) = trace["stages"]
        self.assertEqual((entry["stage"], entry["lights"], entry["duration_ms"]), ("demo", 2, 500))
        self.assertEqual(entry["outcome"], "completed")

    def test_record_without_trace_is_a_no_op(self):
        diagnostics.record("demo", 0.0)


class InventoryStageTests(unittest.TestCase):
    def run_read(self, result, **kwargs):
        trace = {"stages": []}
        token = diagnostics.ACTIVE.set(trace)
        self.addCleanup(diagnostics.ACTIVE.reset, token)
        with patch.object(ha_inventory, "_read_result", return_value=result):
            self.assertIs(ha_inventory.read_result(("u", {}, None), **kwargs), result)
        return trace["stages"]

    def test_success_records_row_count(self):
        (entry,) = self.run_read(ha_inventory.InventoryResult(({"entity_id": "light.a"},)))
        self.assertEqual((entry["stage"], entry["rows"]), ("ha_inventory", 1))

    def test_music_variant_and_failure_are_distinguishable(self):
        (entry,) = self.run_read(ha_inventory.InventoryResult(None, Outcome.UNAVAILABLE), music=True)
        self.assertEqual(entry["stage"], "ha_inventory_music")
        self.assertIsNone(entry["rows"])
        self.assertEqual(entry["outcome"], "unavailable")


class LightStageTests(unittest.TestCase):
    def setUp(self):
        self.ha = fixtures.FakeHomeAssistant()
        self.enterContext(patch.dict(os.environ, fixtures.HA_ENV))
        self.enterContext(patch.object(server, "build_opener", return_value=self.ha))

    def test_light_turn_records_dispatch_and_verify_stages(self):
        trace = {"stages": []}
        token = diagnostics.ACTIVE.set(trace)
        self.addCleanup(diagnostics.ACTIVE.reset, token)
        reply, outcome = server.handle_light_request("turn on the study light and turn off the fairy lights")
        self.assertEqual(outcome, "confirmed", reply)
        stages = {entry["stage"]: entry for entry in trace["stages"]}
        self.assertEqual(stages["lights_dispatch"]["lights"], 2)
        self.assertEqual(stages["lights_verify"]["unconfirmed"], 0)
        self.assertIn("ha_inventory", stages)
        self.assertTrue(all(isinstance(e["duration_ms"], int) for e in trace["stages"]))


if __name__ == "__main__":
    unittest.main()
