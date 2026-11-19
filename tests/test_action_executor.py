import unittest
from declan.ai.action_plan import validate_plan
from declan.ai.action_executor import execute_verified, summarise


class ExecutorTests(unittest.TestCase):
    def setUp(self):
        self.plan = validate_plan({"actions": [
            {"entity_id": "light.a", "service": "turn_on"},
            {"entity_id": "light.b", "service": "turn_on"},
            {"entity_id": "light.c", "service": "turn_off", "depends_on": [0]},
        ]}, {"light.a", "light.b", "light.c"})

    def test_failed_action_skips_dependent_but_runs_independent(self):
        calls = []
        def dispatch(action):
            calls.append(action.entity_id)
            return ("failed", "unavailable") if action.entity_id == "light.a" else ("confirmed", "state verified")
        result = execute_verified(self.plan, dispatch)
        self.assertEqual(calls, ["light.a", "light.b"])
        self.assertEqual([x.status for x in result], ["failed", "confirmed", "skipped_dependency"])
        self.assertEqual(summarise(result)[1], "partial")

    def test_unverified_is_not_success(self):
        result = execute_verified(self.plan[:1], lambda _: ("unverified", "HTTP 200 only"))
        self.assertEqual(summarise(result)[1], "unverified")

    def test_dispatch_exception_does_not_abort_independent(self):
        def dispatch(action):
            if action.entity_id == "light.a":
                raise RuntimeError("secret token")
            return "confirmed", "verified"
        with self.assertLogs("declan.ai.action_executor", level="WARNING") as logs:
            result = execute_verified(self.plan, dispatch)
        self.assertEqual(result[0].detail, "Dispatch or verification failed")
        self.assertEqual(result[1].status, "confirmed")
        # Logged by type so a programming error is not silent, but never with its message.
        self.assertIn("light.a.turn_on (RuntimeError)", logs.output[0])
        self.assertNotIn("secret token", logs.output[0])

    def test_invalid_dispatch_status_fails_closed(self):
        result = execute_verified(self.plan[:1], lambda _: ("success", "sent"))
        self.assertEqual(result[0].status, "failed")


if __name__ == "__main__":
    unittest.main()
