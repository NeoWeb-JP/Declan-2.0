"""Session/training/history orchestration regression tests."""
from typing import Any
import unittest
from unittest.mock import Mock
from declan.turn.turn_persistence_orchestration import finalize_turn


class TurnPersistenceOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.order: list[str]
        self.order = []
        self.state = Mock()
        self.training = Mock()
        self.history = Mock()
        self.state.update_turn.side_effect = self.state_update
        self.training.save_retry_training.side_effect = lambda *a, **k: self.order.append("training")
        self.history.save_turn.side_effect = lambda *a, **k: self.order.append("history")

    def state_update(self, *args, **kwargs):
        self.order.append("state")
        return True

    def finalize(self):
        reply = {"session_id": "session-1", "reply": "Done"}
        session: dict[str, Any]
        session = {}
        finalize_turn(reply, session=session, message="turn off kitchen",
            phrase="turn off kitchen", outcome="confirmed", scope="kitchen",
            status_target="light.kitchen", information_context=None,
            light_result=True, action_results=[{"detail": "confirmed"}],
            actions={"off"}, unmatched_reply="Unmatched", now=123,
            pending_retry={"text": "turn kitchen off"},
            effective_message="turn off kitchen", similar=Mock(),
            normalize_phrase=Mock(), teach_phrase=Mock(), source="assist",
            routine_status={"status": "done"}, phrase_suggestion="turn kitchen off",
            speaker="Jaco", record=Mock(), diagnostic_id=Mock(),
            log_error=Mock(), state_module=self.state,
            training_module=self.training, history_module=self.history)
        return reply, session

    def test_persistence_order(self):
        self.finalize()
        self.assertEqual(self.order, ["state", "training", "history"])

    def test_training_receives_success_from_state(self):
        self.finalize()
        self.assertTrue(self.training.save_retry_training.call_args.kwargs["retry_succeeded"])

    def test_training_receives_failure_from_state(self):
        self.state.update_turn.side_effect = lambda *a, **k: False
        self.finalize()
        self.assertFalse(self.training.save_retry_training.call_args.kwargs["retry_succeeded"])

    def test_history_receives_speaker_and_suggestion(self):
        self.finalize()
        params = self.history.save_turn.call_args.kwargs
        self.assertEqual(params["speaker"], "Jaco")
        self.assertEqual(params["phrase_suggestion"], "turn kitchen off")

    def test_shared_reply_passed_to_all_steps(self):
        reply, session = self.finalize()
        self.assertIs(self.state.update_turn.call_args.args[0], session)
        self.assertIs(self.training.save_retry_training.call_args.args[0], reply)
        self.assertIs(self.history.save_turn.call_args.args[0], reply)
