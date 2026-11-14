"""Contracts for native microphone and secret-preserving settings migration."""
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "declan_two"
SERVER = (ROOT / "server.py").read_text()
PANEL = (COMPONENT / "frontend" / "panel.js").read_text()
INIT = (COMPONENT / "__init__.py").read_text()

class NativeMicrophoneSettingsTests(unittest.TestCase):
    def test_ha_views_parse_and_are_registered(self):
        for name in ("microphone_view.py", "settings_status_view.py"):
            ast.parse((COMPONENT / name).read_text())
        self.assertIn("DeclanMicrophoneView()", INIT)
        self.assertIn("DeclanSettingsStatusView()", INIT)

    def test_audio_relay_requires_admin_and_bounded_pcm(self):
        source = (COMPONENT / "microphone_view.py").read_text()
        for expected in ("not user.is_admin", "application/json", "640000",
                         "len(audio) % 2", "allow_redirects=False", "Bearer {entry.data['token']}"):
            self.assertIn(expected, source)
        self.assertIn('self.path == "/api/stt"', SERVER)
        self.assertIn("secrets.compare_digest(", SERVER)

    def test_spotify_secret_never_sent_to_browser_or_overwritten(self):
        source = (COMPONENT / "settings_status_view.py").read_text()
        self.assertIn("spotify_configured", source)
        self.assertIn("spotify_source", source)
        self.assertNotIn("client_secret", source)
        self.assertIn("window.confirm(", PANEL)
        self.assertIn("form.reset()", PANEL)
        self.assertNotIn("client_secret", source)
        self.assertIn('source in {"saved", "environment"}', SERVER)
        self.assertIn("Existing credentials have not been changed", PANEL)

    def test_microphone_permissions_and_stop_controls(self):
        for expected in ("getUserMedia", "stopMicrophone()", "cancelMicrophone()",
                         "new Int16Array", "16000", "declan_two/microphone",
                         "Stop and transcribe", "Review the text and press Send"):
            self.assertIn(expected, PANEL)

if __name__ == "__main__":
    unittest.main()
