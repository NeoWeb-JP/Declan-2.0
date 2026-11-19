"""Native management regression contracts."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PANEL = (ROOT / "custom_components/declan_two/frontend/panel.js").read_text()
SERVER = (ROOT / "server.py").read_text()
POST_ROUTES = (ROOT / "declan/http/operational_post_routes.py").read_text()
DISPATCH = (ROOT / "declan" / "voice" / "settings_voice_post.py").read_text()
NATIVE_READ = (ROOT / "declan/http/native_read_routes.py").read_text()
VIEW = (ROOT / "custom_components/declan_two/management_view.py").read_text()
INIT = (ROOT / "custom_components/declan_two/__init__.py").read_text()

class NativeManagementContracts(unittest.TestCase):
    def test_management_view_is_registered_and_admin_only(self):
        ast.parse(VIEW)
        self.assertIn("DeclanManagementView()", INIT)
        self.assertIn("not user.is_admin", VIEW)
        self.assertIn("allow_redirects=False", VIEW)
        self.assertIn("Cache-Control", VIEW)

    def test_management_routes_accept_home_assistant_path_parameters(self):
        tree = ast.parse(VIEW)
        view = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "DeclanManagementView")
        for method in ("get", "post"):
            handler = next(node for node in view.body if isinstance(node, ast.AsyncFunctionDef) and node.name == method)
            self.assertEqual([arg.arg for arg in handler.args.args], ["self", "request", "operation"])
        self.assertIn('url = "/api/declan_two/management/{operation}"', VIEW)

    def test_credential_replacement_requires_explicit_confirmation(self):
        self.assertIn('path == "/api/native/spotify-credentials"', DISPATCH)
        ast.parse(POST_ROUTES)
        self.assertIn("operational_post_routes.handle_spotify_credentials(", DISPATCH)
        self.assertIn('set(body) != {"client_id", "client_secret", "confirm"}', POST_ROUTES)
        self.assertIn('body.get("confirm") is not True', POST_ROUTES)
        self.assertIn("window.confirm(", PANEL)
        self.assertIn("form.reset()", PANEL)
        self.assertIn("client_secret", VIEW)
        self.assertNotIn("client_secret", (ROOT / "custom_components/declan_two/settings_status_view.py").read_text())

    def test_read_only_backup_recovery_and_diagnostics(self):
        for endpoint in ("settings-export", "settings-recovery", "diagnostics"):
            self.assertIn("/api/native/" + endpoint, (ROOT / "declan/http/get_access_gate_http.py").read_text())
        self.assertIn("configuration.export()", NATIVE_READ)
        self.assertIn("configuration.recovery()", NATIVE_READ)
        self.assertIn("diagnostics.recent()", NATIVE_READ)
        self.assertIn("declan_two/management/", PANEL)
        self.assertIn("URL.createObjectURL", PANEL)

    def test_chat_and_voice_are_on_overview(self):
        self.assertIn('id="panel-overview"', PANEL)
        self.assertIn('class="overview-chat-heading"', PANEL)
        self.assertIn('id="panel-conversations"', PANEL)
        self.assertIn('data-page="conversations"', PANEL)
        self.assertIn("if (name === 'conversations' && !this._timelineLoaded)", PANEL)
        self.assertLess(PANEL.index('class="chat-form"'), PANEL.index('id="panel-conversations"'))
        self.assertGreater(PANEL.index('class="timeline-list"'), PANEL.index('id="panel-conversations"'))

if __name__ == "__main__":
    unittest.main()
