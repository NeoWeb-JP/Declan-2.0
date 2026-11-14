"""Native conversation history access boundaries and rendering contracts."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = (ROOT / "server.py").read_text()
VIEW = (ROOT / "custom_components/declan_two/history_view.py").read_text()
FRONTEND = (ROOT / "custom_components/declan_two/frontend/panel.js").read_text()


class NativeHistoryContractTests(unittest.TestCase):
    def test_backend_exception_only_matches_history_listing(self):
        source = BACKEND[BACKEND.index("    def do_GET(self):"):BACKEND.index("    def do_POST(self):")]
        self.assertIn('urlsplit(self.path).path == "/api/history"', source)
        self.assertIn('len(token) >= 32', source)
        self.assertIn('not ingress and not history_auth', source)
        self.assertIn('if not ingress and not history_auth and not players_auth and not voice_review_auth and not updates_auth and (', source)
        self.assertIn('self.path == "/api/settings/media-players"', source)
        self.assertIn('not ingress and not capabilities_auth and not history_auth and not players_auth', source)
        self.assertNotIn('self.path.startswith("/api/history") and len(token)', source)

    def test_ha_proxy_requires_admin_and_does_not_forward_metadata(self):
        ast.parse(VIEW)
        self.assertIn('requires_auth = True', VIEW)
        self.assertIn('not user.is_admin', VIEW)
        self.assertIn('allow_redirects=False', VIEW)
        self.assertIn('"Cache-Control": "no-store"', VIEW)
        self.assertIn('payload["turns"][:50]', VIEW)
        self.assertNotIn('"learned_intents":', VIEW)
        self.assertNotIn('"token":', VIEW)

    def test_frontend_renders_history_as_text_not_html(self):
        self.assertIn("this._hass.callApi('GET', path)", FRONTEND)
        self.assertIn('message.textContent = turn.message', FRONTEND)
        self.assertIn('reply.textContent = turn.reply', FRONTEND)
        self.assertIn('list.replaceChildren()', FRONTEND)
        self.assertIn('this._historyCursor', FRONTEND)
        self.assertNotIn('message.innerHTML', FRONTEND)


if __name__ == '__main__':
    unittest.main()
