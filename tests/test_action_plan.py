import unittest

from action_plan import validate_plan, execution_order


class PlanValidationTests(unittest.TestCase):
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
