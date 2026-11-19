"""Regression coverage for extracted domain boundary helpers."""
import unittest
from unittest.mock import Mock

import domain_boundary_helpers as helpers
import server
from execution_results import Outcome


class DomainBoundaryHelperTests(unittest.TestCase):
    def test_outcome_contract_preserves_legacy_strings(self):
        self.assertEqual(server.chained_outcome(Outcome.STARTED.value, Outcome.CONFIRMED.value), Outcome.STARTED.value)
        self.assertIs(server.chained_outcome_result(Outcome.UNVERIFIED, Outcome.UNVERIFIED), Outcome.UNVERIFIED)
        self.assertIs(server.chained_outcome_result(Outcome.FAILED, Outcome.CONFIRMED), Outcome.PARTIAL)

    def test_area_aliases_keep_longest_name(self):
        areas = {"bedroom": set(), "master bedroom": set(), "kitchen": set()}
        labels = helpers.approved_area_labels(areas, room_key=lambda name: "bedroom" if "bedroom" in name else name)
        self.assertEqual(labels["bedroom"], "Master Bedroom")
        self.assertEqual(labels["everywhere"], "Everywhere")

    def test_bounded_plan_passes_cost_and_inventory(self):
        planner, credentials = Mock(), Mock()
        planner.request_plan.return_value = ["one"]
        settings = {"model": "test", "request_ceiling_usd": "0.05", "max_actions": 2}
        result = helpers.bounded_ai_plan("hello", [], settings, inventory={"light": 1},
                                         planner=planner, credentials=credentials, money=lambda value, allow_zero: 50000)
        self.assertEqual(result, ["one"])
        self.assertEqual(planner.request_plan.call_args.kwargs["max_cost_micro_usd"], 50000)
        self.assertEqual(planner.request_plan.call_args.kwargs["inventory"], {"light": 1})
        planner.request_plan.return_value = ["one", "two", "three"]
        with self.assertRaisesRegex(ValueError, "Too many proposed actions"):
            helpers.bounded_ai_plan("hello", [], settings, planner=planner,
                                    credentials=credentials, money=lambda value, allow_zero: 50000)


if __name__ == "__main__":
    unittest.main()
