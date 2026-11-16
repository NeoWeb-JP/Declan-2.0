"""Registered Home Assistant scripts are the only executable routines."""
import unittest
from pathlib import Path
import script_discovery

ROOT = Path(__file__).resolve().parents[1]


class RegisteredScriptTests(unittest.TestCase):
    def test_discovery_excludes_unregistered_services(self):
        source = (ROOT / "custom_components/declan_two/script_discovery_view.py").read_text()
        self.assertIn('hass.services.has_service("script", key)', source)

    def test_good_morning_matches_actual_shared_local_script(self):
        item = {"entity_id": "script.declan_good_morning_shared_local_routine",
                "name": "Declan - Good Morning - Shared Local Routine"}
        self.assertEqual(script_discovery.match("good morning", [item]), ("matched", item))

    def test_ambiguous_scripts_are_never_selected_automatically(self):
        items = [
            {"entity_id": "script.declan_good_morning_shared_local_routine",
             "name": "Declan - Good Morning - Shared Local Routine"},
            {"entity_id": "script.declan_good_morning",
             "name": "Declan - Good Morning"},
        ]
        result = script_discovery.match("good morning", items)
        self.assertEqual(result[0], "ambiguous")


if __name__ == "__main__":
    unittest.main()
