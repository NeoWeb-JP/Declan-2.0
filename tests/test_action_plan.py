import unittest

from action_plan import validate_plan, execution_order
from action_plan import execution_order_result, ActionReadiness
from action_plan import OrderedActionResult


class PlanValidationTests(unittest.TestCase):
    def test_ordered_action_model_rejects_string_statuses_and_malformed_metadata(self):
        action = validate_plan({"actions": [{"entity_id": "light.kitchen", "service": "turn_on"}]},
                               {"light.kitchen"})[0]
        for status in ("pending", "skipped_dependency", None, [], "future_status"):
            with self.subTest(status=status), self.assertRaises(TypeError):
                OrderedActionResult(0, action, status)
        for index in (-1, True, "0", None):
            with self.subTest(index=index), self.assertRaises(ValueError):
                OrderedActionResult(index, action, ActionReadiness.PENDING)
        with self.assertRaises(TypeError):
            OrderedActionResult(0, {"entity_id": "light.kitchen"}, ActionReadiness.PENDING)
        for status in ActionReadiness:
            result = OrderedActionResult(0, action, status)
            self.assertIs(result.status, status)
            self.assertEqual(result.as_legacy_tuple(), (0, action, status.value))
            self.assertIs(type(result.as_legacy_tuple()[2]), str)

    def test_typed_dependency_decisions_observe_live_verified_outcomes(self):
        actions = validate_plan({"actions": [
            {"entity_id": "light.kitchen", "service": "turn_on"},
            {"entity_id": "light.study", "service": "turn_on", "depends_on": [0]},
        ]}, {"light.kitchen", "light.study"})
        for value, expected in ((True, ActionReadiness.PENDING), (False, ActionReadiness.SKIPPED_DEPENDENCY),
                                (1, ActionReadiness.SKIPPED_DEPENDENCY), (None, ActionReadiness.SKIPPED_DEPENDENCY)):
            outcomes = {}
            decisions = execution_order_result(actions, outcomes)
            first = next(decisions)
            self.assertIs(first.action, actions[0])
            self.assertIs(first.status, ActionReadiness.PENDING)
            with self.assertRaises(AttributeError):
                setattr(first, "status", expected)
            outcomes[0] = value
            self.assertIs(next(decisions).status, expected)
            legacy = list(execution_order(actions, outcomes))
            self.assertEqual(legacy[1], (1, actions[1], expected.value))
            self.assertIs(type(legacy[1][2]), str)

    def test_exposed_action(self):
        self.assertEqual(validate_plan({"actions": [{"entity_id": "light.kitchen", "service": "turn_on"}]}, {"light.kitchen"})[0].entity_id, "light.kitchen")

    def test_unexposed_target_rejected(self):
        with self.assertRaises(ValueError):
            validate_plan({"actions": [{"entity_id": "light.private", "service": "turn_off"}]}, {"light.kitchen"})

    def test_injected_fields_rejected(self):
        with self.assertRaises(ValueError):
            validate_plan({"actions": [{"entity_id": "light.kitchen", "service": "turn_on", "url": "https://bad.example"}]}, {"light.kitchen"})

    def test_dangerous_service_rejected(self):
        with self.assertRaises(ValueError):
            validate_plan({"actions": [{"entity_id": "script.goodnight", "service": "reload"}]}, {"script.goodnight"})

    def test_forward_dependency_rejected(self):
        with self.assertRaises(ValueError):
            validate_plan({"actions": [{"entity_id": "light.kitchen", "service": "turn_on", "depends_on": [1]}]}, {"light.kitchen"})

    def test_independent_continues_and_dependent_skips(self):
        actions = validate_plan({"actions": [
            {"entity_id": "light.kitchen", "service": "turn_on"},
            {"entity_id": "light.study", "service": "turn_on"},
            {"entity_id": "light.study", "service": "turn_off", "depends_on": [0]},
        ]}, {"light.kitchen", "light.study"})
        self.assertEqual([status for _, _, status in execution_order(actions, {0: False})], ["pending", "pending", "skipped_dependency"])

    def test_bool_is_not_dependency_index(self):
        with self.assertRaises(ValueError):
            validate_plan({"actions": [{"entity_id": "light.kitchen", "service": "turn_on", "depends_on": [True]}]}, {"light.kitchen"})


if __name__ == "__main__":
    unittest.main()
