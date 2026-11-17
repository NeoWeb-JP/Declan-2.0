"""Fallback retains typed execution, authorization gates and diagnostic redaction."""
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import MagicMock, Mock, patch

from execution_results import ActionResult, ActionStatus, ExecutionResult, Outcome
from fallback_entity_authorization import exposed_entities
from fallback_orchestration import resolve_fallback_result
from guarded_fallback_dispatch import FallbackResponse, dispatch_fallback_result
import server


class TypedFallbackResponseTests(unittest.TestCase):
    def setUp(self):
        self.execution = ExecutionResult("Cannot verify", Outcome.UNVERIFIED, (
            ActionResult(0, "light.study", "light.turn_on", ActionStatus.UNVERIFIED, "No readback"),))
        self.step = {"entity_id": "light.study", "status": "unverified", "ai_generated": True}
        self.actions = []
        self.provider = Mock(return_value=FallbackResponse(self.execution, (self.step,)))
        self.auth = Mock(return_value=("light.study",))
        self.args = dict(routine_reply=None, light_result=None, body={}, authorization="Bearer token",
                         bridge_token="token", source="assist", action_results=self.actions,
                         exposed_entities=self.auth, dispatch_fallback=dispatch_fallback_result,
                         fallback_handler=self.provider)

    def test_dispatch_preserves_identity_evidence_and_appends_steps_once(self):
        with patch.object(ExecutionResult, "as_legacy_pair", side_effect=AssertionError("legacy result")):
            result = resolve_fallback_result("lights", **self.args)
        self.assertIs(result, self.execution)
        self.assertEqual(result.actions, self.execution.actions)
        self.assertEqual(self.actions, [self.step])
        self.provider.assert_called_once_with("lights", source="assist", exposed_entities=("light.study",))
        self.auth.assert_called_once()

    def test_empty_local_results_block_authorization_and_provider(self):
        for changes in ({"routine_reply": ""}, {"light_result": ()}):
            self.assertIsNone(resolve_fallback_result("lights", **(self.args | changes)))
        self.auth.assert_not_called()
        self.provider.assert_not_called()

    def test_unauthorized_entities_never_reach_provider(self):
        args = self.args | dict(exposed_entities=exposed_entities, bridge_token="x" * 32,
                                authorization="Bearer wrong", body={"ai_exposed_entities": ["light.study"]})
        resolve_fallback_result("lights", **args)
        self.assertEqual(self.provider.call_args.kwargs["exposed_entities"], ())

    def test_invalid_provider_results_do_not_append_actions(self):
        for value in (("reply", "invalid", [self.step]), ("reply", "confirmed", ["invalid"]),
                      ("reply", "confirmed", None), ("reply",)):
            self.provider.return_value = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                resolve_fallback_result("lights", **self.args)
            self.assertEqual(self.actions, [])

    def test_legacy_injected_result_is_validated_and_declined_result_is_none(self):
        self.provider.return_value = ("Cannot verify", "unverified", [self.step])
        result = resolve_fallback_result("lights", **self.args)
        self.assertIs(result.outcome, Outcome.UNVERIFIED)
        self.provider.return_value = None
        self.assertIsNone(resolve_fallback_result("lights", **self.args))
        self.assertEqual(self.actions, [self.step])

    def test_server_provider_retains_execution_identity_and_redacts_wire_steps(self):
        inventory = [{"entity_id": "light.study", "state": "off", "attributes": {}}]
        for diagnostics in (False, True):
            settings = dict(server.ai_settings.DEFAULTS, enabled=True, diagnostics=diagnostics)
            with self.subTest(diagnostics=diagnostics), \
                 patch.object(server.ai_settings, "read", return_value=settings), \
                 patch.object(server.ai_intent_gate, "is_action_request", return_value=True), \
                 patch.object(server, "ha_device_connection", return_value=("http://ha", {}, Mock())), \
                 patch.object(server, "read_ha_inventory", return_value=(inventory, None)), \
                 patch.object(server.ai_context, "select", return_value=inventory), \
                 patch.object(server.history, "database", return_value=MagicMock()), \
                 patch.object(server.guarded_fallback, "run_guarded_result", return_value=self.execution) as run, \
                 patch.object(server, "guarded_openai_fallback", side_effect=AssertionError("legacy provider")):
                response = server.guarded_openai_fallback_result("lights on", source="assist", exposed_entities=["light.study"])
            self.assertIs(response.result, self.execution)
            self.assertEqual("detail" in response.action_steps[0], diagnostics)
            self.assertIs(type(response.action_steps[0]["status"]), str)
            run.assert_called_once()

    def test_response_is_frozen_and_legacy_adapter_preserves_plain_triple(self):
        response = FallbackResponse(self.execution, (self.step,))
        with self.assertRaises(FrozenInstanceError):
            response.result = self.execution
        with patch.object(server, "guarded_openai_fallback_result", return_value=response):
            legacy = server.guarded_openai_fallback("lights", source="assist")
        self.assertEqual(legacy, ("Cannot verify", "unverified", [self.step]))
        self.assertIs(type(legacy[1]), str)
        self.assertIs(type(legacy[2]), list)


if __name__ == "__main__":
    unittest.main()
