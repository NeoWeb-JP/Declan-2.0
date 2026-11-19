import unittest

from action_plan import validate_plan, CandidateAction
from ha_action_preflight import preflight


class PreflightTests(unittest.TestCase):
    def test_available_light(self):
        plan = validate_plan({"actions": [{"entity_id": "light.kitchen", "service": "turn_on"}]}, {"light.kitchen"})
        self.assertEqual(preflight(plan, [{"entity_id": "light.kitchen", "state": "off", "attributes": {}}]), plan)

    def test_unavailable_entity(self):
        plan = validate_plan({"actions": [{"entity_id": "light.kitchen", "service": "turn_on"}]}, {"light.kitchen"})
        with self.assertRaises(ValueError):
            preflight(plan, [{"entity_id": "light.kitchen", "state": "unavailable", "attributes": {}}])

    def test_script_requires_confirmation(self):
        plan = validate_plan({"actions": [{"entity_id": "script.night", "service": "turn_on"}]}, {"script.night"})
        row = [{"entity_id": "script.night", "state": "off", "attributes": {}}]
        with self.assertRaises(ValueError):
            preflight(plan, row)
        self.assertEqual(preflight(plan, row, confirmed_sensitive=True), plan)

    def test_garage_requires_sensitive_confirmation(self):
        plan = validate_plan({"actions": [{"entity_id": "cover.garage", "service": "open_cover"}]}, {"cover.garage"})
        row = [{"entity_id": "cover.garage", "state": "closed", "attributes": {"device_class": "garage"}}]
        with self.assertRaises(ValueError):
            preflight(plan, row)
        self.assertEqual(preflight(plan, row, confirmed_sensitive=True), plan)

    def test_toggle_denied(self):
        with self.assertRaises(ValueError):
            validate_plan({"actions": [{"entity_id": "light.kitchen", "service": "toggle"}]}, {"light.kitchen"})
        # Preflight also rejects a caller that bypasses the plan validator.
        plan = (CandidateAction("light.kitchen", "toggle"),)
        with self.assertRaises(ValueError):
            preflight(plan, [{"entity_id": "light.kitchen", "state": "off", "attributes": {}}])

    def test_unverifiable_cover_stop_is_not_advertised_as_executable(self):
        with self.assertRaises(ValueError):
            validate_plan({"actions": [{"entity_id": "cover.blind", "service": "stop_cover"}]}, {"cover.blind"})
        with self.assertRaises(ValueError):
            preflight((CandidateAction("cover.blind", "stop_cover"),),
                      [{"entity_id": "cover.blind", "state": "opening", "attributes": {}}])

    def test_media_feature_required(self):
        plan = validate_plan({"actions": [{"entity_id": "media_player.kitchen", "service": "media_pause"}]}, {"media_player.kitchen"})
        with self.assertRaises(ValueError):
            preflight(plan, [{"entity_id": "media_player.kitchen", "state": "playing", "attributes": {"supported_features": 0}}])


if __name__ == "__main__":
    unittest.main()
