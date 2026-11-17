"""Origin-specific Stop consumes typed Music Assistant control results."""
import unittest
from unittest.mock import patch

import server
from execution_results import ExecutionResult, Outcome


class OriginStopTypedMusicTests(unittest.TestCase):
    def _stop(self, music_result, *, satellite=None):
        inventory = [{"entity_id": "assist_satellite.kitchen",
                      "declan_area": "Kitchen", "declan_device": "kitchen"}]
        with patch.object(server, 'read_music_inventory_result', return_value=(inventory, None)), \
             patch.object(server.music, "control_result", return_value=music_result) as control:
            result, status = server.stop_origin_result("connection", satellite or "assist_satellite.kitchen", None)
        control.assert_called_once()
        return result, status

    def test_confirmed_music_stop_returns_typed_outcome(self):
        with patch.object(server.timers, "stop_due") as stop_due:
            result, status = self._stop(ExecutionResult("Playback stopped.", Outcome.CONFIRMED))
        self.assertIs(result.outcome, Outcome.CONFIRMED)
        self.assertEqual(status, "Playback stopped.")
        stop_due.assert_called_once_with("assist_satellite.kitchen")

    def test_unverified_music_stop_does_not_acknowledge_timer(self):
        with patch.object(server.timers, "stop_due") as stop_due:
            result, status = self._stop(ExecutionResult("Could not verify.", Outcome.UNVERIFIED))
        self.assertIs(result.outcome, Outcome.UNVERIFIED)
        self.assertEqual(status, "Could not verify.")
        stop_due.assert_not_called()

    def test_legacy_wrapper_preserves_music_stop_response(self):
        inventory = [{"entity_id": "assist_satellite.kitchen", "declan_area": "Kitchen",
                      "declan_device": "kitchen"}]
        with patch.object(server, 'read_music_inventory_result', return_value=(inventory, None)), \
             patch.object(server.music, "control_result",
                          return_value=ExecutionResult("Stopped.", Outcome.CONFIRMED)), \
             patch.object(server.timers, "stop_due"):
            self.assertEqual(server.stop_origin_output("connection", "assist_satellite.kitchen", None),
                             ("", "confirmed", "Stopped."))


if __name__ == "__main__":
    unittest.main()
