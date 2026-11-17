"""End-to-end static contract for native AI Settings wiring."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = (ROOT / "server.py").read_text()
AUTHORIZATION = (ROOT / "fallback_entity_authorization.py").read_text()
FALLBACK = (ROOT / "fallback_orchestration.py").read_text()
VIEW = (ROOT / "custom_components/declan_two/ai_settings_view.py").read_text()
INIT = (ROOT / "custom_components/declan_two/__init__.py").read_text()
JS = (ROOT / "custom_components/declan_two/frontend/panel.js").read_text()
HISTORY = (ROOT / "custom_components/declan_two/history_view.py").read_text()


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

    def test_ai_settings_match_native_cards_and_mobile_controls(self):
        self.assertIn('settings-section settings-section--ai', JS)
        self.assertIn('settings-section-icon', JS)
        self.assertIn('class="ai-field"', JS)
        self.assertIn('.ai-settings-form .ai-field input', JS)
        self.assertIn('.ai-domain-grid', JS)
        self.assertIn('grid-template-columns:1fr', JS)
        self.assertNotIn('<details class="settings-section" open>', JS)
        self.assertNotIn('<details class="settings-section settings-section--ai" open>', JS)

    def test_history_proposals_and_diagnostics_are_opt_in(self):
        self.assertIn('showProposals = ai?.settings?.show_proposals === true', JS)
        self.assertIn('if (showProposals && Array.isArray(turn.action_results)', JS)
        self.assertIn('step.ai_generated === true', JS)
        self.assertIn('"action_results": [{', HISTORY)
        self.assertIn('if settings["diagnostics"] else {}', BACKEND)

    def test_fallback_local_first_and_allowlist(self):
        self.assertIn("if routine_reply is not None or light_result is not None:", FALLBACK)
        self.assertIn("fallback_orchestration.resolve_fallback_result(", BACKEND)
        self.assertIn('exposed_entities=fallback_entity_authorization.exposed_entities', BACKEND)
        self.assertIn('exposed = exposed_entities(body, authorization, bridge_token)', FALLBACK)
        self.assertIn('ai_exposed_entities', AUTHORIZATION)
        self.assertIn('authenticated_ha', AUTHORIZATION)
        self.assertIn('ai_pricing.charge(settings["model"]', BACKEND)
        self.assertNotIn("DECLAN_OPENAI_FALLBACK_ENABLED", BACKEND)
        self.assertIn('if not settings["enabled"] or not ai_intent_gate.is_action_request(message):', BACKEND)


if __name__ == "__main__":
    unittest.main()
