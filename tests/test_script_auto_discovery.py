"""Safety and matching regressions for automatic HA script discovery."""
import ast
from pathlib import Path
import re
import unittest
from unittest.mock import patch

import script_discovery

VIEW = Path(__file__).resolve().parents[1] / "custom_components/declan_two/script_discovery_view.py"
tree = ast.parse(VIEW.read_text(encoding="utf-8"))
function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "inspect_script")
namespace = {"re": re, "LIGHT": re.compile(r"light\.[a-z0-9_]+\Z"),
             "SAFE_ACTIONS": {"light.turn_on", "light.turn_off", "light.toggle"}}
exec(compile(ast.Module(body=[function], type_ignores=[]), str(VIEW), "exec"), namespace)
inspect_script = namespace["inspect_script"]


class ScriptSafetyTests(unittest.TestCase):
    def test_explicit_light_action_is_safe(self):
        self.assertTrue(inspect_script({"sequence": [{"action": "light.turn_on",
            "target": {"entity_id": "light.dining_room"}, "data": {"brightness_pct": 30}}]}))

    def test_unknown_and_dangerous_scripts_fail_closed(self):
        for definition in (
            None, {}, {"sequence": []},
            {"sequence": [{"action": "lock.unlock", "target": {"entity_id": "lock.front_door"}}]},
            {"sequence": [{"action": "script.turn_on", "target": {"entity_id": "script.other"}}]},
            {"sequence": [{"action": "light.turn_on", "target": {"area_id": "kitchen"}}]},
            {"sequence": [{"action": "light.turn_on", "target": {"entity_id": "{{ variable }}"}}]},
            {"sequence": [{"choose": [{"conditions": [], "sequence": []}]}]},
            {"sequence": [{"action": "light.turn_on", "target": {"entity_id": "light.kitchen"},
                           "data": {"brightness_pct": "{{ 50 }}"}}]},
            {"sequence": [{"action": "light.turn_on", "target": {"entity_id": "light.kitchen"}}],
             "fields": {"name": {"required": True}}},
        ):
            with self.subTest(definition=definition):
                self.assertFalse(inspect_script(definition))

    def test_natural_alias_and_ambiguity(self):
        safe = {"entity_id": "script.house_status", "name": "House Status", "safe": True}
        self.assertEqual(script_discovery.match("what is the status of the house", [safe]), ("matched", safe))
        self.assertEqual(script_discovery.match("run house status", [safe]), ("matched", safe))
        self.assertEqual(script_discovery.match("house status", [safe, dict(safe, entity_id="script.other")])[0], "ambiguous")
        self.assertIsNone(script_discovery.match("unlock the front door", [safe]))

    def test_declan_prefixed_ha_script_does_not_need_mapping(self):
        script = {"entity_id": "script.declan_good_night",
                  "name": "Declan - Good Night", "safe": False}
        self.assertEqual(script_discovery.match("good night", [script]), ("matched", script))
        self.assertEqual(script_discovery.match("run good night", [script]), ("matched", script))

    def test_all_discovered_scripts_can_be_selected(self):
        protected = {"entity_id": "script.garage", "name": "Garage", "safe": False}
        self.assertEqual(script_discovery.match("garage", [protected]), ("matched", protected))

    def test_missing_ha_opener_fails_closed(self):
        scripts, error = script_discovery.discover(("http://localhost", {}, None))
        self.assertEqual(scripts, [])
        self.assertEqual(error, "inspection_unavailable")

    def test_execution_rejects_script_removed_from_ha(self):
        with patch.object(script_discovery, "discover", return_value=([], None)):
            result = script_discovery.execute(("url", {}, object()), {"entity_id": "script.house_status"})
        self.assertEqual(result[1], "unresolved")

    def test_non_light_script_can_execute_when_present(self):
        from unittest.mock import MagicMock
        opener = MagicMock()
        response = opener.open.return_value.__enter__.return_value
        response.status = 200
        with patch.object(script_discovery, "discover", return_value=(
            [{"entity_id": "script.house_status", "name": "House Status", "safe": False}], None)):
            result = script_discovery.execute(("http://ha", {}, opener), {"entity_id": "script.house_status"})
        self.assertEqual(result[1], "requested")
        self.assertEqual(opener.open.call_count, 1)


if __name__ == "__main__":
    unittest.main()
