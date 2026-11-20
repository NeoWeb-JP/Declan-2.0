"""Registered Home Assistant scripts are the only executable routines."""
import unittest
from pathlib import Path
from declan.ha import script_discovery
from result_pairs import pair_of

ROOT = Path(__file__).resolve().parents[1]


class RegisteredScriptTests(unittest.TestCase):
    def test_discovery_excludes_unregistered_services(self):
        source = (ROOT / "custom_components/declan_two/script_discovery_view.py").read_text()
        self.assertIn('hass.services.has_service("script", key)', source)

    def test_good_morning_matches_actual_shared_local_script(self):
        item = {"entity_id": "script.declan_good_morning_shared_local_routine",
                "name": "Declan - Good Morning - Shared Local Routine"}
        self.assertEqual(pair_of(script_discovery.match_result)("good morning", [item]), ("matched", item))

    def test_good_morning_prefers_unique_response_capable_script(self):
        legacy = {"entity_id": "script.declan_good_morning",
                  "name": "Declan - Good Morning", "fields": []}
        current = {"entity_id": "script.declan_good_morning_shared_local_routine",
                   "name": "Declan - Good Morning - Shared Local Routine",
                   "fields": ["request_id", "routine_id"]}
        self.assertEqual(pair_of(script_discovery.match_result)("good morning", [legacy, current]),
                         ("matched", current))

    def test_two_response_capable_scripts_stay_ambiguous(self):
        items = [
            {"entity_id": "script.declan_good_morning",
             "name": "Declan - Good Morning", "fields": ["request_id", "routine_id"]},
            {"entity_id": "script.declan_good_morning_shared_local_routine",
             "name": "Declan - Good Morning - Shared Local Routine",
             "fields": ["request_id", "routine_id"]},
        ]
        self.assertEqual(pair_of(script_discovery.match_result)("good morning", items)[0], "ambiguous")

    def test_ambiguous_scripts_are_never_selected_automatically(self):
        items = [
            {"entity_id": "script.declan_good_morning_shared_local_routine",
             "name": "Declan - Good Morning - Shared Local Routine"},
            {"entity_id": "script.declan_good_morning",
             "name": "Declan - Good Morning"},
        ]
        result = pair_of(script_discovery.match_result)("good morning", items)
        self.assertEqual(result[0], "ambiguous")


if __name__ == "__main__":
    unittest.main()
