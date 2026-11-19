"""Native media-player mapping authentication and UI contracts."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
AUTH = (ROOT / "post_origin_auth_http.py").read_text()
BACKEND = (ROOT / "server.py").read_text()
MEDIA_ROUTES = (ROOT / "media_settings_routes.py").read_text()
VIEW = (ROOT / "custom_components/declan_two/media_players_view.py").read_text()
INIT = (ROOT / "custom_components/declan_two/__init__.py").read_text()
JS = (ROOT / "custom_components/declan_two/frontend/panel.js").read_text()


class MediaPlayersContractTests(unittest.TestCase):
    def test_backend_token_is_scoped_to_player_settings(self):
        get = BACKEND[BACKEND.index("    def do_GET(self):"):BACKEND.index("    def do_POST(self):")]
        post = BACKEND[BACKEND.index("    def handle_post(self):"):]
        self.assertIn('settings_read_routes.handles(handler.path)', (ROOT / 'get_request_dispatch.py').read_text())
        self.assertIn('"/api/settings/media-players"', (ROOT / "settings_read_routes.py").read_text())
        self.assertIn('get_request_dispatch.dispatch(', get)
        self.assertIn('get_access_gate_http.enforce_access(', (ROOT / 'get_request_dispatch.py').read_text())
        self.assertIn('not players_auth', (ROOT / 'get_access_gate_http.py').read_text())
        self.assertIn('settings_voice_post.handles(self.path)', post)
        self.assertIn('media_settings_post.handles(path)', (ROOT / 'settings_voice_post.py').read_text())
        media_post = (ROOT / "media_settings_post.py").read_text()
        self.assertIn('"/api/settings/media-players"', media_post)
        self.assertIn('handler.approved_player_settings(body)', media_post)
        ast.parse(AUTH)
        self.assertIn('"/api/settings/media-players"', AUTH)
        self.assertIn('secrets.compare_digest(', AUTH)
        self.assertIn("post_request_preflight.enforce(", post)
        self.assertIn("post_origin_auth_http.enforce_access,", post)

    def test_admin_proxy_and_payload_validation(self):
        ast.parse(VIEW)
        self.assertIn('requires_auth = True', VIEW)
        self.assertIn('not user.is_admin', VIEW)
        self.assertIn('set(body) != {"rooms"}', VIEW)
        self.assertIn('allow_redirects": False', VIEW)
        self.assertIn('"Cache-Control": "no-store"', VIEW)
        self.assertIn('DeclanMediaPlayersView()', INIT)

    def test_area_labels_prefer_master_bedroom_over_alias(self):
        import server
        labels = server.approved_area_labels({
            "master bedroom": {"light.bedroom"},
            "bedroom": {"light.bedroom"},
            "living room": {"light.lounge"},
            "lounge": {"light.lounge"},
            "kitchen": {"light.kitchen"},
        })
        self.assertEqual(labels["bedroom"], "Master Bedroom")
        self.assertEqual(labels["living room"], "Living Room")
        self.assertEqual(labels["everywhere"], "Everywhere")
        self.assertEqual(labels["kitchen"], "Kitchen")

    def test_ui_has_save_refresh_and_safe_options(self):
        self.assertIn("this._hass.callApi('GET', 'declan_two/media-players')", JS)
        self.assertIn("this._hass.callApi('POST', 'declan_two/media-players', {rooms})", JS)
        self.assertIn('option.textContent = player.name', JS)
        self.assertIn('data.room_labels && data.room_labels[room]', JS)
        self.assertIn('label.textContent = ', JS)
        ast.parse(MEDIA_ROUTES)
        self.assertIn("media_settings_routes.approved_player_settings(", BACKEND)
        self.assertIn('"room_labels": room_labels', MEDIA_ROUTES)
        self.assertIn('players-save', JS)
        self.assertNotIn('option.innerHTML', JS)
        self.assertNotIn('Bearer ', JS)


if __name__ == "__main__":
    unittest.main()
