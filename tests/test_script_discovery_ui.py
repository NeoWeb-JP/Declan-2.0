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
        self.assertIn("this._scriptDiscovery || []", PANEL)
        self.assertIn("declan_two/script-discovery", PANEL)
        self.assertIn("refine your search", PANEL)

    def test_no_mapping_or_approval_ui(self):
        self.assertIn("No mapping or approval required", PANEL)
        self.assertIn("Available to Declan automatically", PANEL)
        self.assertNotIn("Review / enable", PANEL)
        self.assertNotIn("Protected · approval required", PANEL)
        self.assertIn("declan_two/management/routines", PANEL)

    def test_no_placeholder_mappings_are_saved(self):
        self.assertNotIn("if (!Object.hasOwn(result.routines || {}, name)) this.addRoutineRow", PANEL)


if __name__ == "__main__":
    unittest.main()
