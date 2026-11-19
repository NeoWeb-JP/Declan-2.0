"""Regression tests for response completion orchestration."""
import unittest

from service_doubles import patch_module_collaborators
from types import SimpleNamespace
from unittest.mock import Mock

from declan.turn import turn_response_completion


class ResponseCompletionTests(unittest.TestCase):
    def setUp(self):
        self.r = Mock()
        patch_module_collaborators(self, turn_response_completion, self.r)
        self.r.os.environ = {}
        self.r.SESSION_STORE.sessions = {}
        self.r.SESSION_STORE.lock = Mock()
        self.handler = Mock()
        self.handler.headers = {"Authorization": "Bearer token"}
        self.dispatch = SimpleNamespace(
            reply="initial", outcome="handled", routine_status="ok", routine_turn="routine",
            routine_voice_result="voice", lighting_context="lights", information_context="info",
            status_target="target", light_result="light")
        self.r.turn_response_preparation.prepare.return_value = SimpleNamespace(
            reply="prepared", outcome="prepared-outcome", guest_mode=True,
            visitor_present=False, response_guest_mode=True, information_context="updated-info")
        self.r.turn_atomic_finalization.finalize.return_value = SimpleNamespace(to_wire=lambda: {"ok": True})

    def complete(self):
        return turn_response_completion.complete(
            self.handler, body={"message": "hello"}, message="hello", effective_message="hello",
            session_id="s1", phrase="hello", source="voice", scope="home",
            pending_retry="retry", action_results="evidence", dispatch_result=self.dispatch, services=self.r)

    def test_preparation_runs_before_atomic_finalization(self):
        result = self.complete()
        self.assertEqual(result.to_wire(), {"ok": True})
        self.r.turn_response_preparation.prepare.assert_called_once()
        self.r.turn_atomic_finalization.finalize.assert_called_once()

    def test_prepared_reply_and_context_reach_finalization(self):
        self.complete()
        args = self.r.turn_atomic_finalization.finalize.call_args.args
        self.assertEqual(args[3], "prepared-outcome")
        self.assertEqual(args[7], "prepared")
        self.assertEqual(args[17], "updated-info")
        self.assertEqual(args[18], "retry")

    def test_authorization_and_action_evidence_preserved(self):
        self.complete()
        kwargs = self.r.turn_response_preparation.prepare.call_args.kwargs
        self.assertEqual(kwargs["authorization"], "Bearer token")
        self.assertEqual(kwargs["action_results"], "evidence")
        self.assertEqual(kwargs["information_context"], "info")
        self.assertIs(self.r.turn_atomic_finalization.finalize.call_args.kwargs["log_error"], self.handler.log_error)


if __name__ == "__main__":
    unittest.main()
