"""Model completion, dependency readiness and device success remain distinct."""
import io
import json
import sqlite3
import unittest
from unittest.mock import Mock

from declan.ai.ai_budget import monthly_reserved
from execution_results import ActionStatus, DispatchResult, Outcome
from declan.ai.guarded_fallback import run_guarded_result
from declan.ai.openai_planner import request_plan


class ModelProviderDispatchTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.inventory = [{"entity_id": "light." + name, "state": "off", "attributes": {}}
                          for name in ("kitchen", "study", "hall")]
        self.usage = []

    def response(self, actions, status="completed"):
        return {"status": status, "usage": {"input_tokens": 10, "output_tokens": 2}, "output": [
            {"type": "message", "role": "assistant", "content": [
                {"type": "output_text", "text": json.dumps({"actions": actions})}]}]}

    def run_provider(self, payload, dispatcher):
        opener = Mock()
        opener.open.return_value = io.BytesIO(json.dumps(payload).encode())
        return run_guarded_result("lights on", self.inventory,
            planner=lambda text, exposed: request_plan(text, exposed, opener=opener,
                model="gpt-5-mini", api_key="fixture", usage_sink=self.usage.append),
            dispatcher=dispatcher, budget_db=self.db,
            monthly_limit_micro_usd=1000, request_ceiling_micro_usd=30)

    def test_incomplete_provider_responses_never_dispatch_and_retain_reservations(self):
        for index, status in enumerate(("incomplete", "failed", "future", "COMPLETED", None), 1):
            dispatcher = Mock()
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, "Invalid model plan"):
                self.run_provider(self.response([], status), dispatcher)
            dispatcher.assert_not_called()
            self.assertEqual(monthly_reserved(self.db), index * 30)
            self.assertEqual(len(self.usage), index)

    def test_completed_empty_plan_never_dispatches_or_claims_execution(self):
        dispatcher = Mock()
        result = self.run_provider(self.response([]), dispatcher)
        self.assertIs(result.outcome, Outcome.UNRESOLVED)
        dispatcher.assert_not_called()
        self.assertEqual(monthly_reserved(self.db), 30)

    def test_typed_dispatch_results_control_dependencies_and_final_outcome(self):
        actions = [{"entity_id": "light.kitchen", "service": "turn_on"},
                   {"entity_id": "light.study", "service": "turn_on", "depends_on": [0]},
                   {"entity_id": "light.hall", "service": "turn_on"}]
        dispatcher = Mock(side_effect=[DispatchResult(ActionStatus.UNVERIFIED), DispatchResult(ActionStatus.CONFIRMED)])
        result = self.run_provider(self.response(actions), dispatcher)
        self.assertIs(result.outcome, Outcome.PARTIAL)
        self.assertEqual([call.args[0].entity_id for call in dispatcher.call_args_list], ["light.kitchen", "light.hall"])
        self.assertEqual([action.status for action in result.actions],
                         [ActionStatus.UNVERIFIED, ActionStatus.SKIPPED_DEPENDENCY, ActionStatus.CONFIRMED])
        self.assertEqual(monthly_reserved(self.db), 30)
