"""Verify persisted media search agent validation before HA network access."""
import unittest
from unittest.mock import patch

import server
from execution_results import Outcome


class MediaAgentConfigurationTests(unittest.TestCase):
    def test_invalid_agent_rejected_without_network_access(self):
        for agent in ("sensor.search", "conversation.", "conversation.Agent",
                      "conversation.local/../other", "conversation.local?x=1",
                      "conversation.local#fragment"):
            with self.subTest(agent=agent), patch.object(
                    server.configuration, "get", return_value=agent), patch.object(
                    server, "ha_device_connection") as connection:
                result = server.search_media_result("where can i watch dune")
                self.assertIsNotNone(result)
                self.assertEqual(result.outcome, Outcome.NOT_CONFIGURED)
                connection.assert_not_called()

    def test_invalid_agent_does_not_block_unrelated_phrases(self):
        with patch.object(server.configuration, "get") as config:
            self.assertIsNone(server.search_media_result("turn on the lights"))
            config.assert_not_called()


if __name__ == "__main__":
    unittest.main()
