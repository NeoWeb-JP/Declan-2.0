"""Verify browser timer satellite environment defaults and validation."""
import os
import unittest
from unittest.mock import patch

from declan.timers import timers


class BrowserTimerSatelliteEnvironmentTests(unittest.TestCase):
    def resolve(self, environment, response=None):
        with patch.dict(os.environ, environment, clear=True), patch.object(
                timers, "ha_json", return_value=response) as ha:
            result = timers.resolve_output(
                object(), "assist_satellite.original", "device.original", browser=True)
        return result, ha

    def test_unset_and_empty_values_do_not_fall_back_to_supplied_device(self):
        for settings in ({}, {"DECLAN_BROWSER_TIMER_SATELLITE": ""}, {
                "DECLAN_BROWSER_TIMER_SATELLITE": "   "}):
            with self.subTest(settings=settings):
                result, ha = self.resolve(settings)
                self.assertIsNone(result)
                ha.assert_not_called()

    def test_invalid_satellite_fails_before_home_assistant_request(self):
        for value in ("not-an-entity", "media_player.kitchen", "assist_satellite.", "bad name"):
            with self.subTest(value=value):
                result, ha = self.resolve({"DECLAN_BROWSER_TIMER_SATELLITE": value})
                self.assertIsNone(result)
                ha.assert_not_called()

    def test_valid_override_is_trimmed_and_used_in_template(self):
        entity = "assist_satellite.kitchen"
        result, ha = self.resolve(
            {"DECLAN_BROWSER_TIMER_SATELLITE": "  " + entity + "  "},
            [entity, "Kitchen", "idle"])
        self.assertEqual(result, (entity, "Kitchen"))
        template = ha.call_args.kwargs["data"]["template"]
        self.assertIn(entity, template)
        self.assertNotIn("device.original", template)
        self.assertNotIn("assist_satellite.original", template)

    def test_other_satellite_response_is_not_accepted(self):
        result, ha = self.resolve(
            {"DECLAN_BROWSER_TIMER_SATELLITE": "assist_satellite.kitchen"},
            ["assist_satellite.bedroom", "Bedroom", "idle"])
        self.assertIsNone(result)
        ha.assert_called_once()


if __name__ == "__main__":
    unittest.main()
