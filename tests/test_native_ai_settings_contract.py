"""End-to-end static contract for native AI Settings wiring."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = (ROOT / "server.py").read_text()
VIEW = (ROOT / "custom_components/declan_two/ai_settings_view.py").read_text()
INIT = (ROOT / "custom_components/declan_two/__init__.py").read_text()
JS = (ROOT / "custom_components/declan_two/frontend/panel.js").read_text()


class NativeAISettingsContractTests(unittest.TestCase):
    def test_backend_routes_are_authenticated(self):
        ast.parse(BACKEND)
        self.assertIn('self.path == "/api/settings/ai"', BACKEND)
        self.assertIn('ai_settings.save(body["settings"])', BACKEND)
        self.assertIn('ai_credentials.replace_key(body["api_key"])', BACKEND)
        self.assertIn('secrets.compare_digest(', BACKEND)

    def test_ha_admin_proxy(self):
        ast.parse(VIEW)
        self.assertIn("requires_auth = True", VIEW)
        self.assertIn("not user.is_admin", VIEW)
        self.assertIn("allow_redirects", VIEW)
        self.assertIn("DeclanAISettingsView()", INIT)
        self.assertNotIn("OPENAI_API_KEY", VIEW)

    def test_native_form_and_safe_key_replacement(self):
        self.assertIn("loadAISettings()", JS)
        self.assertIn("saveAISettings()", JS)
        self.assertIn("saveAIKey()", JS)
        self.assertIn("autocomplete=\"new-password\"", JS)
        self.assertIn("form.reset();", JS)
        self.assertNotIn("Bearer ", JS)
        self.assertIn("declan_two/ai-settings", JS)

    def test_fallback_local_first_and_allowlist(self):
        self.assertIn("if routine_reply is None and light_result is None:", BACKEND)
        self.assertIn('ai_exposed_entities', BACKEND)
        self.assertIn('authenticated_ha', BACKEND)
        self.assertIn('ai_pricing.charge(settings["model"]', BACKEND)


if __name__ == "__main__":
    unittest.main()
