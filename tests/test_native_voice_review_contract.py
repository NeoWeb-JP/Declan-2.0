"""Voice review is authenticated and strictly read-only."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SERVER = (ROOT / "server.py").read_text()
VIEW = (ROOT / "custom_components/declan_two/voice_review_view.py").read_text()
JS = (ROOT / "custom_components/declan_two/frontend/panel.js").read_text()
INIT = (ROOT / "custom_components/declan_two/__init__.py").read_text()


class VoiceReviewContractTests(unittest.TestCase):
    def test_backend_exception_only_allows_get(self):
        get = SERVER[SERVER.index("    def do_GET(self):"):SERVER.index("    def do_POST(self):")]
        post = SERVER[SERVER.index("    def handle_post(self):"):]
        self.assertIn('self.path == "/api/voicepipeline"', get)
        self.assertIn('not voice_review_auth', get)
        self.assertNotIn('voice_review_auth', post)

    def test_ha_view_requires_admin_and_never_writes(self):
        ast.parse(VIEW)
        self.assertIn('requires_auth = True', VIEW)
        self.assertIn('not user.is_admin', VIEW)
        self.assertIn('allow_redirects=False', VIEW)
        self.assertIn('"Cache-Control": "no-store"', VIEW)
        self.assertNotIn('async def post(', VIEW)
        self.assertIn('DeclanVoiceReviewView()', INIT)

    def test_ui_displays_plain_text_without_controls_that_change_profiles(self):
        self.assertIn("this._hass.callApi('GET', 'declan_two/voice-review')", JS)
        self.assertIn('transcript.textContent = interaction.transcript', JS)
        self.assertIn('name.textContent = profile.name', JS)
        self.assertNotIn('transcript.innerHTML', JS)


if __name__ == "__main__":
    unittest.main()
