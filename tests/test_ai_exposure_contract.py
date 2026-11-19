"""Verify AI exposure is supplied by HA, not untrusted client input."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
EXPOSURE = (ROOT / "custom_components/declan_two/ai_exposure.py").read_text()
AGENT = (ROOT / "custom_components/declan_two/conversation.py").read_text()
CHAT = (ROOT / "custom_components/declan_two/chat_view.py").read_text()
SERVER = (ROOT / "server.py").read_text()
AI_FALLBACK = (ROOT / "ai_fallback_dispatch.py").read_text()
AUTHORIZATION = (ROOT / "fallback_entity_authorization.py").read_text()
FALLBACK = (ROOT / "fallback_orchestration.py").read_text()
PREPARATION = (ROOT / "turn_response_preparation.py").read_text()
COMPLETION = (ROOT / "turn_response_completion.py").read_text()


class AIExposureContractTests(unittest.TestCase):
    def test_ha_assist_exposure_source(self):
        ast.parse(EXPOSURE)
        self.assertIn('async_get_should_expose(hass, "conversation", entity_id)', EXPOSURE)
        self.assertIn('return []', EXPOSURE)

    def test_native_ha_requests_supply_exposure(self):
        self.assertIn('"ai_exposed_entities": exposed_for_declan(self.hass)', AGENT)
        self.assertIn('"ai_exposed_entities": exposed_for_declan(hass)', CHAT)

    def test_backend_rejects_untrusted_exposure(self):
        self.assertIn('turn_response_preparation.prepare(', COMPLETION)
        self.assertIn('fallback_orchestration.resolve_fallback_result(', PREPARATION)
        self.assertIn('exposed_entities=fallback_entity_authorization.exposed_entities', COMPLETION)
        self.assertIn('exposed = exposed_entities(body, authorization, bridge_token)', FALLBACK)
        self.assertIn('if authenticated_ha else ()', AUTHORIZATION)
        self.assertIn('if not permitted or len(permitted)', AI_FALLBACK)
        self.assertNotIn('DECLAN_OPENAI_ALLOWED_ENTITIES', SERVER)


if __name__ == "__main__":
    unittest.main()
