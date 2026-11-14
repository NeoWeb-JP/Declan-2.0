"""Playback from reviewed recordings must reuse the authenticated voice audio proxy."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PANEL = (ROOT / "custom_components/declan_two/frontend/panel.js").read_text()
VIEW = (ROOT / "custom_components/declan_two/voice_review_view.py").read_text()

class ReviewedRecordingPlaybackTests(unittest.TestCase):
    def test_reviewed_rows_offer_playback(self):
        history = PANEL[PANEL.index("  async loadVoiceHistory()"):PANEL.index("  async loadVoices()")]
        self.assertIn("if (item.id)", history)
        self.assertIn("playVoice(item.id, playback, status)", history)
        self.assertIn("playback.setAttribute('aria-label', 'Play reviewed recording')", history)

    def test_existing_secure_audio_path_reused(self):
        self.assertIn("async playVoice(interactionId, button, feedbackStatus = null)", PANEL)
        self.assertIn("feedbackStatus || this.shadowRoot.querySelector('.voices-status')", PANEL)
        self.assertIn("operation: 'audio', interaction_id: interactionId", PANEL)
        self.assertIn('raw[:4] != b"RIFF"', VIEW)
        self.assertIn("not user.is_admin", VIEW)

if __name__ == "__main__":
    unittest.main()
