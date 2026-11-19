"""Inventory and stop boundary regression contracts."""
import unittest
from unittest.mock import Mock, patch

import inventory_stop_boundaries as boundaries
import server


class InventoryStopBoundaryTests(unittest.TestCase):
    def test_inventory_wire_format_uses_live_typed_callback(self):
        r = Mock()
        r.read_ha_inventory_result.return_value.as_legacy_pair.return_value = ("inventory", "ok")
        self.assertEqual(boundaries.read_ha_inventory(None, r=r), ("inventory", "ok"))

    def test_music_inventory_is_requested_with_music_flag(self):
        r = Mock()
        boundaries.read_music_inventory_result("connection", r=r)
        r.ha_inventory.read_result.assert_called_once_with("connection", music=True)

    def test_stop_everywhere_keeps_status_and_outcome(self):
        r = Mock()
        typed = Mock()
        typed.reply = "stopped"
        typed.outcome.value = "confirmed"
        r.stop_everywhere_result.return_value = (typed, 200)
        self.assertEqual(boundaries.stop_everywhere_output("connection", r=r), ("stopped", "confirmed", 200))

    def test_stop_origin_forwards_timer_and_music_providers(self):
        r = Mock()
        boundaries.stop_origin_result("connection", "satellite", "device", r=r)
        kwargs = r.music_stop_dispatch.stop_origin_result.call_args.kwargs
        self.assertIs(kwargs["timer_provider"], r.timers)
        self.assertIs(kwargs["music_provider"], r.music)
        self.assertIs(kwargs["inventory_reader"], r.read_music_inventory_result)

    def test_switch_dispatch_preserves_preview_and_evidence(self):
        r = Mock()
        boundaries.set_switch_as_light_result("fan", "on", {}, None, preview=True, r=r)
        kwargs = r.ha_area_switch_actions.set_switch_as_light_result.call_args.kwargs
        self.assertTrue(kwargs["preview"])
        self.assertIs(kwargs["append_evidence"], r.append_action_evidence)

    def test_public_wrapper_uses_patched_inventory_reader(self):
        typed = Mock()
        typed.as_legacy_pair.return_value = ("items", "ok")
        with patch.object(server, "read_ha_inventory_result", return_value=typed):
            self.assertEqual(server.read_ha_inventory(None), ("items", "ok"))


if __name__ == "__main__":
    unittest.main()
