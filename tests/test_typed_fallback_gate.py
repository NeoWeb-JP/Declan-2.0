"""Typed fallback gate: authorization, precedence and result validation."""
from typing import Any
import unittest
from unittest.mock import Mock

from declan.core.execution_results import ExecutionResult, Outcome
from declan.ai.fallback_orchestration import resolve_fallback_result


class TypedFallbackGateTests(unittest.TestCase):
    def setUp(self):
        self.authorize = Mock(return_value=("light.allowed",))
        self.dispatch = Mock(return_value=ExecutionResult("Done", Outcome.CONFIRMED))
        self.handler = Mock()
        self.actions: list[dict[str, Any]]
        self.actions = []
        self.kwargs = dict(
            routine_reply=None, light_result=None,
            body={"ai_exposed_entities": ["light.allowed"]},
            authorization="Bearer token", bridge_token="token",
            source="assist", action_results=self.actions,
            exposed_entities=self.authorize,
            dispatch_fallback=self.dispatch, fallback_handler=self.handler,
        )

    def resolve(self, **changes):
        return resolve_fallback_result("hello", **(self.kwargs | changes))

    def test_typed_result_is_preserved(self):
        self.assertIs(self.resolve(), self.dispatch.return_value)
        self.authorize.assert_called_once_with(
            self.kwargs["body"], "Bearer token", "token")
        self.dispatch.assert_called_once_with(
            "hello", source="assist", exposed_entities=("light.allowed",),
            fallback_handler=self.handler, action_results=self.actions)

    def test_local_reply_blocks_authorization_and_dispatch(self):
        self.assertIsNone(self.resolve(routine_reply=""))
        self.authorize.assert_not_called()
        self.dispatch.assert_not_called()

    def test_local_lighting_blocks_authorization_and_dispatch(self):
        self.assertIsNone(self.resolve(light_result=()))
        self.authorize.assert_not_called()
        self.dispatch.assert_not_called()

    def test_unhandled_fallback_returns_none(self):
        self.dispatch.return_value = None
        self.assertIsNone(self.resolve())

    def test_legacy_result_is_rejected(self):
        self.dispatch.return_value = ("Done", "confirmed")
        with self.assertRaisesRegex(ValueError, "typed execution result"):
            self.resolve()

    def test_dispatch_error_propagates(self):
        self.dispatch.side_effect = RuntimeError("offline")
        with self.assertRaisesRegex(RuntimeError, "offline"):
            self.resolve()


if __name__ == "__main__":
    unittest.main()
