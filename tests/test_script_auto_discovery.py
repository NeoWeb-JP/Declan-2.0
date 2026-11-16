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
        self.assertEqual(script_discovery.match("what is the status of the house", [safe]), ("safe", safe))
        self.assertEqual(script_discovery.match("run house status", [safe]), ("safe", safe))
        self.assertEqual(script_discovery.match("house status", [safe, dict(safe, entity_id="script.other")])[0], "ambiguous")
        self.assertIsNone(script_discovery.match("unlock the front door", [safe]))

    def test_protected_scripts_are_never_auto_selected(self):
        protected = {"entity_id": "script.garage", "name": "Garage", "safe": False}
        self.assertEqual(script_discovery.match("garage", [protected]), ("protected", protected))

    def test_reinspection_blocks_script_that_became_unsafe(self):
        with patch.object(script_discovery, "discover", return_value=(
            [{"entity_id": "script.house_status", "name": "House Status", "safe": False}], None)):
            result = script_discovery.execute(("url", {}, object()), {"entity_id": "script.house_status"})
        self.assertEqual(result[1], "unresolved")


if __name__ == "__main__":
    unittest.main()
