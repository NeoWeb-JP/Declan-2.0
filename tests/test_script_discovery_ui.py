"""Contracts for automatic HA script discovery without a redundant settings UI."""
from pathlib import Path
import unittest

PANEL = (Path(__file__).resolve().parents[1] /
         "custom_components/declan_two/frontend/panel.js").read_text(encoding="utf-8")
DISCOVERY = (Path(__file__).resolve().parents[1] / "declan" / "ha" / "script_discovery.py").read_text(encoding="utf-8")


class ScriptDiscoveryUITests(unittest.TestCase):
    def test_read_only_script_browser_removed_from_settings(self):
        self.assertNotIn('settings-section--routines', PANEL)
        self.assertNotIn('class="routine-search"', PANEL)
        self.assertNotIn('class="routine-discovery"', PANEL)
        self.assertNotIn('class="routines-refresh"', PANEL)
        self.assertNotIn("void this.loadRoutines(); void this.loadSettingsStatus()", PANEL)

    def test_automatic_discovery_still_available_to_voice_commands(self):
        self.assertIn("def discover_result(", DISCOVERY)
        self.assertIn("def execute_result(", DISCOVERY)
        self.assertNotIn("Review / enable", PANEL)
        self.assertNotIn("Protected · approval required", PANEL)

    def test_no_placeholder_mappings_are_saved(self):
        self.assertNotIn("if (!Object.hasOwn(result.routines || {}, name)) this.addRoutineRow", PANEL)


if __name__ == "__main__":
    unittest.main()
