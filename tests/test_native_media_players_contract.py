"""Native media-player mapping authentication and UI contracts."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = (ROOT / "server.py").read_text()
VIEW = (ROOT / "custom_components/declan_two/media_players_view.py").read_text()
INIT = (ROOT / "custom_components/declan_two/__init__.py").read_text()
JS = (ROOT / "custom_components/declan_two/frontend/panel.js").read_text()


class MediaPlayersContractTests(unittest.TestCase):
    def test_backend_token_is_scoped_to_player_settings(self):
        get = BACKEND[BACKEND.index("    def do_GET(self):"):BACKEND.index("    def do_POST(self):")]
        post = BACKEND[BACKEND.index("    def handle_post(self):"):]
        self.assertIn('self.path == "/api/settings/media-players"', get)
        self.assertIn('not players_auth', get)
        self.assertIn('self.path == "/api/settings/media-players"', post)
        self.assertIn('secrets.compare_digest(', post)

    def test_admin_proxy_and_payload_validation(self):
        ast.parse(VIEW)
        self.assertIn('requires_auth = True', VIEW)
        self.assertIn('not user.is_admin', VIEW)
        self.assertIn('set(body) != {"rooms"}', VIEW)
        self.assertIn('allow_redirects": False', VIEW)
        self.assertIn('"Cache-Control": "no-store"', VIEW)
        self.assertIn('DeclanMediaPlayersView()', INIT)

    def test_ui_has_save_refresh_and_safe_options(self):
        self.assertIn("this._hass.callApi('GET', 'declan_two/media-players')", JS)
        self.assertIn("this._hass.callApi('POST', 'declan_two/media-players', {rooms})", JS)
        self.assertIn('option.textContent = player.name', JS)
        self.assertIn('label.textContent = room', JS)
        self.assertIn('players-save', JS)
        self.assertNotIn('option.innerHTML', JS)
        self.assertNotIn('Bearer ', JS)


if __name__ == "__main__":
    unittest.main()
