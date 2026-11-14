"""Contract checks for native voice review and recording playback."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
VIEW = (ROOT / "custom_components/declan_two/voice_review_view.py").read_text()
PANEL = (ROOT / "custom_components/declan_two/frontend/panel.js").read_text()
SERVER = (ROOT / "server.py").read_text()


class NativeVoicePlaybackContract(unittest.TestCase):
    def test_view_requires_admin_and_scopes_audio(self):
        ast.parse(VIEW)
        self.assertIn("not user.is_admin", VIEW)
        self.assertIn('set(body) != {"operation", "interaction_id"}', VIEW)
        self.assertIn('base64.b64decode(encoded, validate=True)', VIEW)
        self.assertIn('raw[:4] != b"RIFF"', VIEW)
        self.assertIn('allow_redirects=False', VIEW)

    def test_backend_limits_remote_audio_requests(self):
        self.assertIn('body.get("operation") not in {"resolve", "audio"}', SERVER)
        self.assertIn('set(body) != {"operation", "interaction_id"}', SERVER)

    def test_native_panel_handles_unknown_and_audio(self):
        self.assertIn("['unknown', 'unidentified', 'none']", PANEL)
        self.assertIn("operation: 'audio'", PANEL)
        self.assertIn("URL.revokeObjectURL(url)", PANEL)
        self.assertIn("feedback = error?.message", PANEL)


if __name__ == "__main__":
    unittest.main()
