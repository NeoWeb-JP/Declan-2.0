"""Dependency health must not confuse recent activity with current reachability."""
from typing import Any, cast
import unittest

from declan.http import health_readiness
from declan.ha.home_assistant_results import HomeAssistantStatus, HomeAssistantStatusResult


class HomeAssistantReadinessPolicyTests(unittest.TestCase):
    def test_only_connected_is_ready(self):
        for status in HomeAssistantStatus:
            with self.subTest(status=status):
                result = HomeAssistantStatusResult(status)
                self.assertEqual(
                    health_readiness.home_assistant_ready(result),
                    status is HomeAssistantStatus.CONNECTED,
                )

    def test_rejects_untyped_status_strings(self):
        with self.assertRaises(TypeError):
            cast(Any, health_readiness.home_assistant_ready)("connected")


if __name__ == "__main__":
    unittest.main()
