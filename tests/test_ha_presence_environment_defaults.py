"""Verify HA guest and visitor state readers reject unsafe environment settings."""
import os
import unittest
from unittest.mock import patch

import server


class HomeAssistantPresenceEnvironmentTests(unittest.TestCase):
    def test_guest_mode_missing_or_invalid_connection_does_not_call_network(self):
        settings = ({}, {"DECLAN_HA_URL": "https://ha.example"},
                    {"DECLAN_HA_URL": "https://ha.example", "DECLAN_HA_TOKEN": " "},
                    {"DECLAN_HA_URL": "ftp://ha.example", "DECLAN_HA_TOKEN": "token"},
                    {"DECLAN_HA_URL": "https://user@ha.example", "DECLAN_HA_TOKEN": "token"},
                    {"DECLAN_HA_URL": "https://ha.example/?key=x", "DECLAN_HA_TOKEN": "token"})
        for environment in settings:
            with self.subTest(environment=environment), patch.dict(
                    os.environ, environment, clear=True), patch.object(
                    server, "build_opener") as opener:
                self.assertIsNone(server.read_guest_mode())
                opener.assert_not_called()

    def test_visitor_presence_missing_or_invalid_connection_does_not_call_network(self):
        settings = ({}, {"DECLAN_HA_URL": "https://ha.example"},
                    {"DECLAN_HA_URL": "https://ha.example", "DECLAN_HA_TOKEN": " "},
                    {"DECLAN_HA_URL": "file:///tmp/test", "DECLAN_HA_TOKEN": "token"},
                    {"DECLAN_HA_URL": "https://ha.example/#fragment", "DECLAN_HA_TOKEN": "token"})
        for environment in settings:
            with self.subTest(environment=environment), patch.dict(
                    os.environ, environment, clear=True), patch.object(
                    server, "build_opener") as opener:
                self.assertIsNone(server.read_visitors_present())
                opener.assert_not_called()


if __name__ == "__main__":
    unittest.main()
