"""Verify AI exposure is supplied by HA, not untrusted client input."""
import ast
from pathlib import Path
import unittest
from unittest.mock import Mock
from declan.ai.fallback_entity_authorization import exposed_entities
from declan.ai.fallback_orchestration import resolve_fallback_result
from declan.ai.guarded_fallback_dispatch import dispatch_fallback_result

ROOT = Path(__file__).resolve().parents[1]
EXPOSURE = (ROOT / "custom_components/declan_two/ai_exposure.py").read_text()
AGENT = (ROOT / "custom_components/declan_two/conversation.py").read_text()
CHAT = (ROOT / "custom_components/declan_two/chat_view.py").read_text()


class AIExposureContractTests(unittest.TestCase):
    def load_exposure(self, helper):
        import importlib.util
        import sys
        from types import ModuleType, SimpleNamespace
        module = ModuleType("homeassistant.components.homeassistant.exposed_entities")
        if helper is not None:
            setattr(module, "async_should_expose", helper)
        parent = ModuleType("homeassistant.components.homeassistant")
        setattr(parent, "exposed_entities", module)
        modules = {"homeassistant": ModuleType("homeassistant"),
                   "homeassistant.components": ModuleType("homeassistant.components"),
                   "homeassistant.components.homeassistant": parent,
                   "homeassistant.components.homeassistant.exposed_entities": module}
        spec = importlib.util.spec_from_file_location(
            "ai_exposure_fixture", ROOT / "custom_components/declan_two/ai_exposure.py")
        assert spec is not None and spec.loader is not None
        loaded = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loaded)
        states = [SimpleNamespace(entity_id=entity) for entity in (
            "light.kitchen", "light.secret", "media_player.lounge_tv", "lock.front_door", "switch.kettle")]
        hass = SimpleNamespace(states=SimpleNamespace(async_all=lambda: states))
        from unittest.mock import patch
        with patch.dict(sys.modules, modules):
            return loaded.exposed_for_declan(hass)

    def test_uses_home_assistants_real_exposure_helper(self):
        # HA exports async_should_expose(hass, assistant, entity_id). The old code
        # imported a name that doesn't exist, so AI device control was always refused.
        calls = []

        def async_should_expose(hass, assistant, entity_id):
            calls.append(assistant)
            return entity_id != "light.secret"
        self.assertEqual(self.load_exposure(async_should_expose),
                         ["light.kitchen", "media_player.lounge_tv", "switch.kettle"])
        self.assertEqual(set(calls), {"conversation"})

    def test_missing_helper_fails_closed(self):
        with self.assertLogs(level="WARNING"):
            self.assertEqual(self.load_exposure(None), [])
        ast.parse(EXPOSURE)
        self.assertNotIn("async_get_should_expose", EXPOSURE)

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
