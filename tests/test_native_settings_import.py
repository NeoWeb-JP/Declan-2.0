"""Native configuration import remains preview-first and does not touch credentials."""
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]
SERVER = (ROOT / "server.py").read_text()
VIEW = (ROOT / "custom_components/declan_two/management_view.py").read_text()
PANEL = (ROOT / "custom_components/declan_two/frontend/panel.js").read_text()
CONFIG = (ROOT / "configuration.py").read_text()

class NativeImportContracts(unittest.TestCase):
    def test_backend_reuses_atomic_validated_import(self):
        ast.parse(SERVER)
        ast.parse(VIEW)
        self.assertIn('"/api/native/settings-import"', SERVER)
        self.assertIn('configuration.preview(body.get(\'document\'))', SERVER)
        self.assertIn("configuration.apply(body.get('document'), body.get('expected'))", SERVER)
        self.assertIn("def validate(document):", CONFIG)
        self.assertIn("Settings changed since preview", CONFIG)
        self.assertIn("settings_recovery", CONFIG)

    def test_admin_proxy_is_explicit_and_bounded(self):
        self.assertIn('not user.is_admin', VIEW)
        self.assertIn('operation not in {"spotify", "import"}', VIEW)
        self.assertIn('request.content_length <= (131072 if operation == "import" else 2048)', VIEW)
        self.assertIn('set(body) not in ({"document"}, {"document", "confirm", "expected"})', VIEW)
        self.assertIn('"/api/native/settings-import"', VIEW)

    def test_ui_requires_preview_and_confirmation(self):
        self.assertIn('class="settings-import-file"', PANEL)
        self.assertIn('class="settings-import-apply" type="button" disabled', PANEL)
        self.assertIn("this.resetSettingsImport()", PANEL)
        self.assertIn("this._settingsImportPreview = null", PANEL)
        self.assertIn("window.confirm('Apply the reviewed settings import?", PANEL)
        self.assertIn("expected: preview.expected, confirm: true", PANEL)
        self.assertIn("Spotify credentials are never imported", PANEL)

if __name__ == "__main__":
    unittest.main()
