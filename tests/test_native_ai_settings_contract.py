"""End-to-end static contract for native AI Settings wiring."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
POST_INGRESS = (ROOT / "post_ingress_orchestration.py").read_text()
BACKEND = (ROOT / "server.py").read_text()
AI_FALLBACK = (ROOT / "ai_fallback_dispatch.py").read_text()
AI_POST = (ROOT / "ai_settings_post.py").read_text()
DISPATCH = (ROOT / "settings_voice_post.py").read_text()
AUTHORIZATION = (ROOT / "fallback_entity_authorization.py").read_text()
FALLBACK = (ROOT / "fallback_orchestration.py").read_text()
PREPARATION = (ROOT / "turn_response_preparation.py").read_text()
VIEW = (ROOT / "custom_components/declan_two/ai_settings_view.py").read_text()
INIT = (ROOT / "custom_components/declan_two/__init__.py").read_text()
JS = (ROOT / "custom_components/declan_two/frontend/panel.js").read_text()
HISTORY = (ROOT / "custom_components/declan_two/history_view.py").read_text()


class NativeAISettingsContractTests(unittest.TestCase):
    def test_backend_routes_are_authenticated(self):
        ast.parse(BACKEND)
        ast.parse(AI_POST)
        self.assertIn('path == "/api/settings/ai"', DISPATCH)
        self.assertIn("ai_settings_post.handle_ai_settings(", DISPATCH)
        self.assertIn("ai_save=r.ai_settings.save", POST_INGRESS)
        self.assertIn("ai_replace_key=r.ai_credentials.replace_key", POST_INGRESS)
        self.assertIn('save(body["settings"])', AI_POST)
        self.assertIn('replace_key(body["api_key"])', AI_POST)
        ingress = (ROOT / "http_ingress_security.py").read_text()
        ast.parse(ingress)
        self.assertIn("http_ingress_security.has_ingress_access(self)", BACKEND)
        self.assertIn("secrets.compare_digest(", ingress)

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
        self.assertIn('evidence_factory.from_action(action, include_detail=settings["diagnostics"])', AI_FALLBACK)

    def test_fallback_local_first_and_allowlist(self):
        self.assertIn("if routine_reply is not None or light_result is not None:", FALLBACK)
        self.assertIn('turn_response_preparation.prepare(', BACKEND)
        self.assertIn('fallback_orchestration.resolve_fallback_result(', PREPARATION)
        self.assertIn('exposed_entities=fallback_entity_authorization.exposed_entities', BACKEND)
        self.assertIn('exposed = exposed_entities(body, authorization, bridge_token)', FALLBACK)
        self.assertIn('ai_exposed_entities', AUTHORIZATION)
        self.assertIn('authenticated_ha', AUTHORIZATION)
        self.assertIn('pricing(settings["model"]', AI_FALLBACK)
        self.assertNotIn("DECLAN_OPENAI_FALLBACK_ENABLED", BACKEND)
        self.assertIn('if not settings["enabled"] or not intent_gate(message):', AI_FALLBACK)


if __name__ == "__main__":
    unittest.main()
