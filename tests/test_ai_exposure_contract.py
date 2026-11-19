"""Verify AI exposure is supplied by HA, not untrusted client input."""
import ast
from pathlib import Path
import unittest
from unittest.mock import Mock
from fallback_entity_authorization import exposed_entities
from fallback_orchestration import resolve_fallback_result
from guarded_fallback_dispatch import dispatch_fallback_result

ROOT = Path(__file__).resolve().parents[1]
EXPOSURE = (ROOT / "custom_components/declan_two/ai_exposure.py").read_text()
AGENT = (ROOT / "custom_components/declan_two/conversation.py").read_text()
CHAT = (ROOT / "custom_components/declan_two/chat_view.py").read_text()


class AIExposureContractTests(unittest.TestCase):
    def test_ha_assist_exposure_source(self):
        ast.parse(EXPOSURE)
        self.assertIn('async_get_should_expose(hass, "conversation", entity_id)', EXPOSURE)
        self.assertIn('return []', EXPOSURE)

    def test_native_ha_requests_supply_exposure(self):
        self.assertIn('"ai_exposed_entities": exposed_for_declan(self.hass)', AGENT)
        self.assertIn('"ai_exposed_entities": exposed_for_declan(hass)', CHAT)

    def test_backend_rejects_untrusted_exposure(self):
        body = {'ai_exposed_entities': ['light.private']}
        token = 'x' * 32
        for authorization, bridge_token, expected in (
                ('Bearer wrong', token, ()), ('Bearer short', 'short', ()),
                ('Bearer ' + token, token, ['light.private'])):
            provider = Mock(return_value=None)
            resolve_fallback_result('lights on', routine_reply=None, light_result=None,
                body=body, authorization=authorization, bridge_token=bridge_token,
                source='assist', action_results=[], exposed_entities=exposed_entities,
                dispatch_fallback=dispatch_fallback_result, fallback_handler=provider)
            provider.assert_called_once_with('lights on', source='assist', exposed_entities=expected)


if __name__ == "__main__":
    unittest.main()
