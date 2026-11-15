import sqlite3
import unittest
from action_plan import validate_plan
from ai_budget import monthly_reserved
from guarded_fallback import run_guarded_fallback


class GuardedFallbackTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.inventory = [{"entity_id": "light.kitchen", "state": "off", "attributes": {}}]
        self.plan = validate_plan({"actions": [{"entity_id": "light.kitchen", "service": "turn_on"}]}, {"light.kitchen"})

    def tearDown(self):
        self.db.close()

    def run_pipeline(self, **kwargs):
        return run_guarded_fallback(
            "turn on kitchen", self.inventory, budget_db=self.db,
            monthly_limit_micro_usd=100, request_ceiling_micro_usd=30,
            **kwargs,
        )

    def test_verified_action(self):
        calls = []
        result = self.run_pipeline(
            planner=lambda text, exposed: self.plan,
            dispatcher=lambda action: (calls.append(action.entity_id) or ("confirmed", "observed on")),
            charge_micro_usd=lambda: 10,
        )
        self.assertEqual(calls, ["light.kitchen"])
        self.assertEqual(result["outcome"], "confirmed")

    def test_budget_denies_before_planner_or_dispatch(self):
        self.run_pipeline(planner=lambda *_: (), dispatcher=lambda *_: ("confirmed", ""))
        calls = []
        with self.assertRaises(ValueError):
            self.run_pipeline(planner=lambda *_: calls.append("planned"), dispatcher=lambda *_: calls.append("sent"))
        self.assertEqual(calls, [])

    def test_missing_charge_retains_ceiling(self):
        self.run_pipeline(planner=lambda *_: self.plan, dispatcher=lambda *_: ("unverified", ""))
        self.assertEqual(monthly_reserved(self.db), 30)

    def test_unavailable_device_never_dispatched(self):
        self.inventory[0]["state"] = "unavailable"
        calls = []
        with self.assertRaises(ValueError):
            self.run_pipeline(planner=lambda *_: self.plan,
                              dispatcher=lambda *_: calls.append("sent"))
        self.assertEqual(calls, [])

    def test_empty_plan_no_dispatch(self):
        calls = []
        result = self.run_pipeline(planner=lambda *_: (), dispatcher=lambda *_: calls.append("sent"))
        self.assertEqual(result["outcome"], "unresolved")
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
