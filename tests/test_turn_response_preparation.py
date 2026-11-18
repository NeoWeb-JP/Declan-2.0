"""Guarded fallback and persona response preparation tests."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import turn_response_preparation as stage


class ResponsePreparationTests(unittest.TestCase):
    def setUp(self):
        self.kwargs = dict(
            routine_reply="handled", outcome="done", light_result=None,
            body={}, authorization="Bearer secret", bridge_token="token",
            source="assist", action_results=[], exposed_entities=object(),
            dispatch_fallback=object(), fallback_handler=object(),
            guest_mode_reader=object(), visitors_reader=object(),
            personality_policy=object(), chat_commands={"time": "time"},
            information_context="existing",
        )

    def test_handled_reply_retained_without_fallback(self):
        with patch.object(stage.fallback_orchestration, "resolve_fallback_result", return_value=None) as fallback, patch.object(
            stage.response_persona_context, "resolve_response_persona",
            return_value=(False, False, "Home"),
        ):
            result = stage.prepare("hello", **self.kwargs)
        self.assertEqual((result.reply, result.outcome, result.information_context), ("handled", "done", "existing"))
        self.assertEqual(result.response_guest_mode, "Home")
        self.assertEqual(fallback.call_args.kwargs["authorization"], "Bearer secret")
        self.assertEqual(fallback.call_args.kwargs["bridge_token"], "token")

    def test_fallback_overrides_reply_and_outcome(self):
        fallback = SimpleNamespace(reply="fallback", outcome="answered")
        with patch.object(stage.fallback_orchestration, "resolve_fallback_result", return_value=fallback), patch.object(
            stage.response_persona_context, "resolve_response_persona", return_value=(True, True, "Guest"),
        ):
            result = stage.prepare("unknown", **self.kwargs)
        self.assertEqual((result.reply, result.outcome, result.response_guest_mode), ("fallback", "answered", "Guest"))

    def test_time_context_only_when_no_reply(self):
        self.kwargs["routine_reply"] = None
        with patch.object(stage.fallback_orchestration, "resolve_fallback_result", return_value=None), patch.object(
            stage.response_persona_context, "resolve_response_persona", return_value=(False, False, "Home"),
        ):
            result = stage.prepare("Time?!", **self.kwargs)
        self.assertEqual(result.information_context, ("time", None, None))


if __name__ == "__main__":
    unittest.main()
