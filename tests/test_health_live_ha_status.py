"""A recent Assist turn is not evidence of current Home Assistant reachability."""
import unittest
from unittest.mock import patch

import server
from declan.ha.home_assistant_results import HomeAssistantStatus, HomeAssistantStatusResult


class HomeAssistantDependencyReadinessTests(unittest.TestCase):
    def test_status_vocabulary_distinguishes_live_connection_from_recent_assist(self):
        self.assertIsNot(HomeAssistantStatus.ASSIST_RECENT, HomeAssistantStatus.CONNECTED)

    def test_recent_assist_fallback_when_ha_not_configured(self):
        with patch.dict(server.os.environ, {"DECLAN_HA_URL": "", "DECLAN_HA_TOKEN": ""}):
            with patch.object(server.history, "has_recent_assist", return_value=True):
                result = server.home_assistant_status_result()
        self.assertEqual(result, HomeAssistantStatusResult(HomeAssistantStatus.ASSIST_RECENT))

    def test_connected_status_is_the_only_ready_dependency_status(self):
        self.assertEqual(
            [status for status in HomeAssistantStatus if status is HomeAssistantStatus.CONNECTED],
            [HomeAssistantStatus.CONNECTED],
        )


if __name__ == "__main__":
    unittest.main()
