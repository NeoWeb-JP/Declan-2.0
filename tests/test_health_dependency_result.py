"""Typed dependency health keeps HTTP serialization at the boundary."""
import unittest

from health_readiness import DependencyHealth
from home_assistant_results import HomeAssistantStatus, HomeAssistantStatusResult


class DependencyHealthResultTests(unittest.TestCase):
    def test_all_ha_statuses_and_database_states(self):
        for database in (False, True):
            for status in HomeAssistantStatus:
                with self.subTest(database=database, status=status):
                    result = DependencyHealth(database, HomeAssistantStatusResult(status))
                    expected_ready = database and status is HomeAssistantStatus.CONNECTED
                    code, payload = result.response()
                    self.assertEqual(result.ready, expected_ready)
                    self.assertEqual(code, 200 if expected_ready else 503)
                    self.assertEqual(payload, {
                        "status": "ok" if expected_ready else "unavailable",
                        "database": "ok" if database else "unavailable",
                        "home_assistant": status.value,
                    })

    def test_result_is_immutable(self):
        from dataclasses import FrozenInstanceError
        result = DependencyHealth(True, HomeAssistantStatusResult(HomeAssistantStatus.CONNECTED))
        with self.assertRaises(FrozenInstanceError):
            setattr(result, 'database', False)


if __name__ == "__main__":
    unittest.main()
