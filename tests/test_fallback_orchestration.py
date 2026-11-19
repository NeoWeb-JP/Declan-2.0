"""Regression tests for fallback eligibility and authorization boundaries."""
from typing import Any
import unittest
from unittest.mock import Mock

from declan.ai.fallback_orchestration import resolve_fallback
from declan.ai.fallback_entity_authorization import exposed_entities
from declan.ai.guarded_fallback_dispatch import dispatch_fallback


class FallbackOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.args: dict[str, Any]
        self.auth = Mock(return_value=("light.kitchen",))
        self.fallback = Mock(return_value=("AI reply", "confirmed", ["action"]))
        self.actions: list[dict[str, Any]]
        self.actions = []
        self.args = dict(
            routine_reply=None, light_result=None,
            body={"ai_exposed_entities": ["light.kitchen"]},
            authorization="Bearer token", bridge_token="token",
            source="assist", action_results=self.actions,
            exposed_entities=self.auth, dispatch_fallback=dispatch_fallback,
            fallback_handler=self.fallback,
        )

    def resolve(self, **changes):
        return resolve_fallback("hello", **(self.args | changes))

    def test_unhandled_request_uses_fallback(self):
        self.assertEqual(self.resolve(), ("AI reply", "confirmed"))

    def test_routine_reply_blocks_fallback(self):
        self.assertIsNone(self.resolve(routine_reply="handled"))
        self.fallback.assert_not_called()
        self.auth.assert_not_called()

    def test_empty_routine_reply_blocks_fallback(self):
        self.assertIsNone(self.resolve(routine_reply=""))
        self.auth.assert_not_called()

    def test_light_result_blocks_fallback(self):
        self.assertIsNone(self.resolve(light_result=("on", "confirmed")))
        self.auth.assert_not_called()

    def test_empty_light_result_blocks_fallback(self):
        self.assertIsNone(self.resolve(light_result=()))
        self.auth.assert_not_called()

    def test_fallback_none_does_not_change_actions(self):
        self.fallback.return_value = None
        self.assertIsNone(self.resolve())
        self.assertEqual(self.actions, [])

    def test_fallback_appends_actions(self):
        self.resolve()
        self.assertEqual(self.actions, ["action"])

    def test_authorization_result_forwarded(self):
        self.resolve()
        self.assertEqual(self.fallback.call_args.kwargs["exposed_entities"], ("light.kitchen",))

    def test_source_forwarded(self):
        self.resolve()
        self.assertEqual(self.fallback.call_args.kwargs["source"], "assist")

    def test_original_message_forwarded(self):
        self.resolve()
        self.assertEqual(self.fallback.call_args.args, ("hello",))

    def test_auth_receives_credentials(self):
        self.resolve()
        self.auth.assert_called_once_with(
            self.args["body"], "Bearer token", "token",
        )

    def test_unauthorized_client_cannot_expose_entities(self):
        self.args["exposed_entities"] = exposed_entities
        self.args["bridge_token"] = "x" * 32
        self.args["authorization"] = "Bearer wrong"
        self.resolve()
        self.assertEqual(self.fallback.call_args.kwargs["exposed_entities"], ())

    def test_authorized_client_can_expose_entities(self):
        self.args["exposed_entities"] = exposed_entities
        token = "x" * 32
        self.args["bridge_token"] = token
        self.args["authorization"] = "Bearer " + token
        self.resolve()
        self.assertEqual(self.fallback.call_args.kwargs["exposed_entities"], ["light.kitchen"])

    def test_short_token_never_authorizes(self):
        self.args["exposed_entities"] = exposed_entities
        self.resolve()
        self.assertEqual(self.fallback.call_args.kwargs["exposed_entities"], ())

    def test_fallback_failure_propagates(self):
        self.fallback.side_effect = RuntimeError("unavailable")
        with self.assertRaises(RuntimeError):
            self.resolve()


if __name__ == "__main__":
    unittest.main()
