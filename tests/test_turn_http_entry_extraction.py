"""Regression tests for HTTP turn orchestration and early exits."""
import unittest

from service_doubles import patch_module_collaborators
from types import SimpleNamespace
from unittest.mock import Mock

from declan.turn import turn_http_entry


class TurnHTTPEntryTests(unittest.TestCase):
    def setUp(self):
        self.handler = Mock()
        self.r = Mock()
        patch_module_collaborators(self, turn_http_entry, self.r)
        self.r.post_ingress_orchestration.prepare.return_value = ({"source": "web"}, "hello", "session")
        self.r.turn_session_preflight.prepare.return_value = SimpleNamespace(
            session_id="session", phrase="hello", effective_message="hello",
            pending_retry=None, source="web", scope=None, origin_device=None,
            satellite=None, last_lights=(), last_device=None, last_information=None,
        )
        self.r.turn_response_completion.complete.return_value.to_wire.return_value = {"reply": "hello"}

    def test_ingress_early_exit_does_not_dispatch(self):
        self.r.post_ingress_orchestration.prepare.return_value = None
        turn_http_entry.handle_post(self.handler, services=self.r)
        self.r.turn_session_preflight.prepare.assert_not_called()
        self.r.turn_dispatch_orchestration.dispatch.assert_not_called()
        self.handler.send_json.assert_not_called()

    def test_preflight_early_exit_does_not_dispatch(self):
        self.r.turn_session_preflight.prepare.return_value = None
        turn_http_entry.handle_post(self.handler, services=self.r)
        self.r.turn_dispatch_orchestration.dispatch.assert_not_called()
        self.handler.send_json.assert_not_called()

    def test_dispatch_evidence_and_response_preserved(self):
        turn_http_entry.handle_post(self.handler, services=self.r)
        dispatch = self.r.turn_dispatch_orchestration.dispatch.call_args
        self.assertEqual(dispatch.args, ("hello",))
        self.assertIs(dispatch.kwargs["action_results"], self.r.ActionEvidenceBuffer.return_value)
        self.assertIs(dispatch.kwargs["services"], self.r)
        completion = self.r.turn_response_completion.complete.call_args
        self.assertIs(completion.kwargs["dispatch_result"], self.r.turn_dispatch_orchestration.dispatch.return_value)
        self.assertIs(completion.kwargs["action_results"], dispatch.kwargs["action_results"])
        self.handler.send_json.assert_called_once_with(200, {"reply": "hello"})


if __name__ == "__main__":
    unittest.main()
