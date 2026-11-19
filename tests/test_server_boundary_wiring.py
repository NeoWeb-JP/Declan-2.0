"""Server-level wiring for inventory, stop and switch-light boundaries."""
import unittest
from unittest.mock import Mock, patch

import server


class ServerBoundaryWiringTests(unittest.TestCase):
    def test_music_inventory_is_requested_with_music_flag(self):
        with patch.object(server.ha_inventory, "read_result") as read:
            server.read_music_inventory_result("connection")
        read.assert_called_once_with("connection", music=True)

    def test_stop_origin_forwards_timer_and_music_providers_and_live_reader(self):
        with patch.object(server.music_stop_dispatch, "stop_origin_result") as stop:
            server.stop_origin_result("connection", "satellite", "device")
        kwargs = stop.call_args.kwargs
        self.assertIs(kwargs["timer_provider"], server.timers)
        self.assertIs(kwargs["music_provider"], server.music)
        self.assertIs(kwargs["inventory_reader"], server.read_music_inventory_result)

    def test_stop_everywhere_uses_patchable_typed_core(self):
        with patch.object(server, "_stop_everywhere_typed_core", return_value="sentinel"):
            self.assertEqual(server.stop_everywhere_result(None), "sentinel")

    def test_switch_dispatch_preserves_preview_and_evidence(self):
        with patch.object(server.ha_area_switch_actions, "set_switch_as_light_result", Mock()) as dispatch:
            server.set_switch_as_light_result("fan", "on", [], None, preview=True)
        kwargs = dispatch.call_args.kwargs
        self.assertTrue(kwargs["preview"])
        self.assertIs(kwargs["append_evidence"], server.append_action_evidence)
        self.assertIs(kwargs["request_factory"], server.Request)


if __name__ == "__main__":
    unittest.main()
