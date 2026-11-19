"""Verify visitor entity configuration validation before Home Assistant access."""
import os
import sqlite3
import unittest
from unittest.mock import patch

import server


class VisitorEntityConfigurationTests(unittest.TestCase):
    def test_invalid_visitor_entity_fails_before_network_access(self):
        for entity in ("", "sensor.visitors", "input_boolean.", "input_boolean.Guest",
                       "input_boolean.guests/../../other", "input_boolean.guests?x=1",
                       "input_boolean.guests#fragment", " input_boolean.guests "):
            with self.subTest(entity=entity), patch.dict(os.environ, {
                    "DECLAN_HA_URL": "https://ha.example",
                    "DECLAN_HA_TOKEN": "test-token"}, clear=True), patch.object(
                    server.configuration, "get", return_value=entity), patch.object(
                    server, "build_opener") as opener:
                self.assertIsNone(server.read_visitors_present())
                opener.assert_not_called()

    def test_unavailable_settings_database_is_unknown_without_network(self):
        with patch.dict(os.environ, {
                "DECLAN_HA_URL": "https://ha.example",
                "DECLAN_HA_TOKEN": "test-token"}, clear=True), patch.object(
                server.configuration, "get", side_effect=sqlite3.OperationalError("database locked")
        ), patch.object(server, "build_opener") as opener:
            self.assertIsNone(server.read_visitors_present())
            opener.assert_not_called()

    def test_malformed_non_string_entity_is_unknown(self):
        for entity in (None, 42, [], {}):
            with self.subTest(entity=entity), patch.dict(os.environ, {
                    "DECLAN_HA_URL": "https://ha.example",
                    "DECLAN_HA_TOKEN": "test-token"}, clear=True), patch.object(
                    server.configuration, "get", return_value=entity
            ), patch.object(server, "build_opener") as opener:
                self.assertIsNone(server.read_visitors_present())
                opener.assert_not_called()

    def test_missing_credentials_or_invalid_url_never_opens_connection(self):
        cases = (
            {"DECLAN_HA_URL": "https://ha.example"},
            {"DECLAN_HA_TOKEN": "test-token"},
            {"DECLAN_HA_URL": "ftp://ha.example", "DECLAN_HA_TOKEN": "test-token"},
            {"DECLAN_HA_URL": "https://user@ha.example", "DECLAN_HA_TOKEN": "test-token"},
            {"DECLAN_HA_URL": "https://ha.example/?x=1", "DECLAN_HA_TOKEN": "test-token"},
        )
        for settings in cases:
            with self.subTest(settings=settings), patch.dict(os.environ, settings, clear=True), patch.object(
                    server, "build_opener") as opener:
                self.assertIsNone(server.read_visitors_present())
                opener.assert_not_called()

    def test_valid_visitor_entity_is_used_in_fixed_state_endpoint(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return b'{"state":"on"}'

        class Opener:
            def open(self, request, timeout):
                self.request = request
                self.timeout = timeout
                return Response()

        opener = Opener()
        with patch.dict(os.environ, {"DECLAN_HA_URL": "https://ha.example/",
                                     "DECLAN_HA_TOKEN": " test-token "}, clear=True), patch.object(
                server.configuration, "get", return_value="input_boolean.visitors"), patch.object(
                server, "build_opener", return_value=opener):
            self.assertIs(server.read_visitors_present(), True)
        self.assertEqual(opener.request.full_url,
                         "https://ha.example/api/states/input_boolean.visitors")
        self.assertEqual(opener.request.get_header("Authorization"), "Bearer test-token")
        self.assertEqual(opener.timeout, 1)


if __name__ == "__main__":
    unittest.main()
