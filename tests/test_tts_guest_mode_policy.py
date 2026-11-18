"""Guest Mode fallback safety and alternative household entity selection."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "custom_components" / "declan_two" / "guest_mode_policy.py"
SPEC = importlib.util.spec_from_file_location("test_guest_mode_policy", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Unable to load Guest Mode policy")
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)


class GuestModePolicyTests(unittest.TestCase):
    def test_legacy_default_remains_compatible(self):
        self.assertEqual(policy.guest_mode_entity(policy.DEFAULT_GUEST_MODE_ENTITY),
                         "input_boolean.guest_mode")
        hass = SimpleNamespace(states=Mock(get=Mock(return_value=SimpleNamespace(state="off"))))
        self.assertFalse(policy.guest_safe(hass))
        hass.states.get.assert_called_once_with("input_boolean.guest_mode")

    def test_alternative_guest_mode_entity_is_used_for_privacy(self):
        helper = "input_boolean.house_sitter_mode"
        hass = SimpleNamespace(states=Mock())
        for state, expected in (("off", False), ("on", True),
                                ("unknown", True), ("unavailable", True)):
            with self.subTest(state=state):
                hass.states.get.return_value = SimpleNamespace(state=state)
                self.assertEqual(policy.guest_safe(hass, helper), expected)
                hass.states.get.assert_called_with(helper)

    def test_missing_and_invalid_state_never_enables_private_sass(self):
        hass = SimpleNamespace(states=Mock(get=Mock(return_value=None)))
        self.assertTrue(policy.guest_safe(hass))
        for helper in ("sensor.motion", "input_boolean.", "input_boolean.BadCase",
                       "input_boolean.guest/../other", "", None):
            with self.subTest(helper=helper):
                hass.states.get.reset_mock()
                self.assertTrue(policy.guest_safe(hass, helper))
                hass.states.get.assert_not_called()
                with self.assertRaises(ValueError):
                    policy.guest_mode_entity(helper)

    def test_state_registry_absent_is_private(self):
        self.assertTrue(policy.guest_safe(SimpleNamespace()))


if __name__ == "__main__":
    unittest.main()
