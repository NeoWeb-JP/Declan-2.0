"""Read-only reviewed VoicePipeline recordings in native HA panel."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
VIEW = (ROOT / "custom_components/declan_two/voice_review_view.py").read_text()
SERVER = (ROOT / "server.py").read_text()
PANEL = (ROOT / "custom_components/declan_two/frontend/panel.js").read_text()


class NativeVoiceHistoryTests(unittest.TestCase):
    def test_proxy_limits_history_request_and_response(self):
        ast.parse(VIEW)
        self.assertIn('request.query.get("history") == "1"', VIEW)
        self.assertIn('set(request.query) != {"history"}', VIEW)
        self.assertIn('json={"operation": "history"}', VIEW)
        self.assertIn('data["interactions"][:100]', VIEW)
        self.assertIn('"Cache-Control": "no-store"', VIEW)

    def test_backend_allows_only_read_history_shape(self):
        self.assertIn('body.get("operation") == "history" and set(body) != {"operation"}', SERVER)

    def test_panel_history_is_read_only(self):
        self.assertIn("declan_two/voice-review?history=1", PANEL)
        self.assertIn("item.current_assigned_to || item.matched_speaker", PANEL)
        self.assertIn("transcript.textContent = item.transcript", PANEL)


if __name__ == "__main__":
    unittest.main()
