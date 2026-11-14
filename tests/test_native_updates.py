"""Native backend updater must remain admin-only and reuse server update safety."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
VIEW = (ROOT / "custom_components/declan_two/updates_view.py").read_text()
PANEL = (ROOT / "custom_components/declan_two/frontend/panel.js").read_text()
INIT = (ROOT / "custom_components/declan_two/__init__.py").read_text()


class NativeUpdaterTests(unittest.TestCase):
    def test_admin_and_credential_boundary(self):
        self.assertIn('user is None or not user.is_admin', VIEW)
        self.assertIn('requires_auth = True', VIEW)
        self.assertIn('entry.data[\'token\']', VIEW)
        self.assertIn('allow_redirects": False', VIEW)
        self.assertIn('Cache-Control": "no-store"', VIEW)
        self.assertNotIn('entry.data[\'token\']', PANEL)

    def test_fixed_backend_routes_and_validated_requests(self):
        self.assertIn('"/api/updates/status"', VIEW)
        self.assertIn('"/api/updates"', VIEW)
        self.assertIn('type(body.get("include_prereleases")) is not bool', VIEW)
        self.assertIn('VERSION.fullmatch(body["version"])', VIEW)
        self.assertIn('DeclanUpdatesView()', INIT)

    def test_panel_checks_selects_and_installs_explicitly(self):
        for phrase in ('async checkUpdates()', 'async installUpdate()', 'async loadUpdateStatus()',
                       'Include prerelease versions', 'Install selected release',
                       "window.confirm('Install Declan backend release", 'declan_two/updates'):
            self.assertIn(phrase, PANEL)
        self.assertNotIn('Use the existing Declan updater for now.', PANEL)
