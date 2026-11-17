"""Verify Home Assistant status environment defaults and URL guards."""
import os
import unittest
from unittest.mock import patch

import server


class HomeAssistantStatusEnvironmentTests(unittest.TestCase):
    def status(self, settings):
        with patch.dict(os.environ, settings, clear=True), patch.object(
                server.history, "has_recent_assist", return_value=False), patch.object(
                server, "build_opener") as opener:
            result = server.home_assistant_status_result()
            opener.assert_not_called()
            return result.status.value

    def test_missing_or_blank_credentials_are_unconfigured(self):
        for settings in ({}, {"DECLAN_HA_URL": ""}, {"DECLAN_HA_TOKEN": ""},
                         {"DECLAN_HA_URL": "https://ha.example", "DECLAN_HA_TOKEN": "  "}):
            with self.subTest(settings=settings):
                self.assertEqual(self.status(settings), "not_configured")

    def test_invalid_urls_fail_before_network_access(self):
        for url in ("ftp://ha.example", "ha.example", "https://user:pass@ha.example",
                    "https://ha.example/?token=secret", "https://ha.example/#fragment",
                    "https://"):
            with self.subTest(url=url):
                self.assertEqual(self.status({
                    "DECLAN_HA_URL": url, "DECLAN_HA_TOKEN": "test-token"}), "not_configured")

    def test_recent_assist_is_used_when_credentials_missing(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(
                server.history, "has_recent_assist", return_value=True), patch.object(
                server, "build_opener") as opener:
            result = server.home_assistant_status_result()
            self.assertEqual(result.status.value, "assist_recent")
            opener.assert_not_called()


if __name__ == "__main__":
    unittest.main()
