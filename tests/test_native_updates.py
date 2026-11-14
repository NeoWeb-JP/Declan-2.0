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

    def test_endpoint_rejects_unauthorized_and_malformed_requests(self):
        import asyncio
        import importlib.util
        import sys
        import types
        from unittest.mock import patch

        modules = {}
        for name in ("aiohttp", "aiohttp.web", "homeassistant",
                     "homeassistant.components", "homeassistant.components.http",
                     "homeassistant.helpers", "homeassistant.helpers.aiohttp_client"):
            module = types.ModuleType(name)
            modules[name] = module
        modules["aiohttp"].web = modules["aiohttp.web"]
        modules["aiohttp.web"].json_response = lambda body, status=200, **kw: (status, body)
        modules["homeassistant.components.http"].HomeAssistantView = type("HomeAssistantView", (), {})
        modules["homeassistant.helpers.aiohttp_client"].async_get_clientsession = lambda hass: None
        modules["aiohttp"].ClientError = type("ClientError", (Exception,), {})
        modules["aiohttp"].ClientTimeout = lambda **kw: kw

        spec = importlib.util.spec_from_file_location("declan_updates_test_view",
            ROOT / "custom_components/declan_two/updates_view.py")
        with patch.dict(sys.modules, modules):
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            view = module.DeclanUpdatesView()

            class Request(dict):
                content_type = "application/json"
                content_length = 100
                async def json(self):
                    return self["body"]

            def request(user, body):
                obj = Request(hass_user=user, body=body)\n                obj.app = {"hass": types.SimpleNamespace(config_entries=types.SimpleNamespace(async_entries=lambda domain: []))}\n                return obj

            async def run():
                admin = types.SimpleNamespace(is_admin=True)
                guest = types.SimpleNamespace(is_admin=False)
                self.assertEqual((await view.get(request(guest, {})))[0], 403)
                self.assertEqual((await view.get(request(None, {})))[0], 403)
                self.assertEqual((await view.post(request(guest, {})))[0], 400)
                self.assertEqual((await view.post(request(admin, {})))[0], 400)
                for body in (
                    {"operation": "check", "include_prereleases": "false"},
                    {"operation": "install", "include_prereleases": False, "version": "../bad"},
                    {"operation": "install", "include_prereleases": False, "version": "1.0.0", "extra": True},
                ):
                    self.assertEqual((await view.post(request(admin, body)))[0], 400)
                for operation in ("check", "install"):
                    body = {"operation": operation, "include_prereleases": False}
                    if operation == "install":
                        body["version"] = "1.2.3"
                    self.assertEqual((await view.post(request(admin, body)))[0], 503)
            asyncio.run(run())
