"""Regression checks for manually assigning Unknown voice recordings."""
from pathlib import Path
import unittest

PANEL = (Path(__file__).resolve().parents[1] / "custom_components/declan_two/frontend/panel.js").read_text()

class NativeUnknownSpeakerContract(unittest.TestCase):
    def test_confirm_uses_selected_speaker(self):
        self.assertIn("confirm.disabled = !select.value", PANEL)
        self.assertIn("select.addEventListener('change'", PANEL)
        self.assertIn("known && select.value === suggested ? 'confirm' : 'assign'", PANEL)
        self.assertIn("this.resolveVoice(interaction.id, action, select.value)", PANEL)
        self.assertNotIn("this.resolveVoice(interaction.id, 'confirm', interaction.matched_speaker)", PANEL)

    def test_voice_review_refreshes_after_save(self):
        self.assertIn("this._voicesPending = false;\n      await this.loadVoices();", PANEL)

if __name__ == "__main__":
    unittest.main()
