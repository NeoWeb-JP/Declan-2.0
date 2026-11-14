"""Native conversations and voice views use compact accessible subtabs."""
from pathlib import Path
import unittest

PANEL = (Path(__file__).resolve().parents[1] / "custom_components/declan_two/frontend/panel.js").read_text()

class NativeActivityTabsTests(unittest.TestCase):
    def test_single_main_activity_tab(self):
        self.assertIn('data-tab="activity"', PANEL)
        self.assertNotIn('data-tab="voices"', PANEL)
        self.assertNotIn('data-tab="conversations"', PANEL)
        self.assertIn('id="panel-activity"', PANEL)

    def test_four_subtabs_have_panels(self):
        for name in ('conversations', 'review', 'reviewed', 'profiles'):
            self.assertIn('data-activity="' + name + '"', PANEL)
            self.assertIn('id="activity-' + name + '"', PANEL)
        self.assertIn("panel.hidden = panel.id !== 'activity-' + name", PANEL)
        self.assertIn("tab.setAttribute('aria-selected', String(active))", PANEL)

    def test_existing_actions_remain_wired(self):
        for fragment in ("this.loadHistory()", "this.loadVoices()", "this.loadVoiceHistory()",
                         "this.loadVoiceProfiles()", "this.resolveVoice(interaction.id, action, select.value)",
                         "this.correctVoiceHistory(item, select.value)", "this.playVoice(interaction.id, play)"):
            self.assertIn(fragment, PANEL)

    def test_profiles_loaded_before_history_corrections(self):
        self.assertIn("if (!this._voiceProfilesLoaded) await this.loadVoiceProfiles();", PANEL)
        self.assertIn("await this.loadVoiceHistory();", PANEL)

if __name__ == "__main__":
    unittest.main()
