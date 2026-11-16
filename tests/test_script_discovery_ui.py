"""Contracts for searchable Home Assistant script discovery UI."""
from pathlib import Path
import unittest

PANEL = (Path(__file__).resolve().parents[1] /
         "custom_components/declan_two/frontend/panel.js").read_text(encoding="utf-8")


class ScriptDiscoveryUITests(unittest.TestCase):
    def test_search_and_bounded_rendering(self):
        self.assertIn('class="routine-search"', PANEL)
        self.assertIn("renderScriptDiscovery()", PANEL)
        self.assertIn("matches.slice(0, 40)", PANEL)
        self.assertIn("entity.entity_id?.startsWith('script.')", PANEL)
        self.assertIn("refine your search", PANEL)

    def test_existing_mappings_remain_editable(self):
        self.assertIn('class="settings-subsection routine-overrides"', PANEL)
        self.assertIn("this.addRoutineRow(name, item)", PANEL)
        self.assertIn("declan_two/management/routines", PANEL)
        self.assertIn("Customise", PANEL)

    def test_no_placeholder_mappings_are_saved(self):
        self.assertNotIn("if (!Object.hasOwn(result.routines || {}, name)) this.addRoutineRow", PANEL)


if __name__ == "__main__":
    unittest.main()
