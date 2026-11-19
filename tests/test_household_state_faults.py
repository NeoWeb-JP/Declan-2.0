"""Regression coverage for unavailable and malformed household HA state replies."""
import json
import os
import sqlite3
import unittest
from unittest.mock import patch

import server


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit):
        return json.dumps(self.payload).encode()


class Opener:
    def __init__(self, payload):
        self.payload = payload

    def open(self, _request, timeout):
        assert timeout == 1
        return Response(self.payload)


class HouseholdStateFaultTests(unittest.TestCase):
    def setUp(self):
        self.credentials = patch.dict(os.environ, {
            "DECLAN_HA_URL": "https://ha.example",
            "DECLAN_HA_TOKEN": "test-token",
        }, clear=True)
        self.credentials.start()
        self.addCleanup(self.credentials.stop)

    def test_guest_mode_non_object_payload_returns_unknown(self):
        payload: object
        for payload in (None, [], "on", 42):
            with self.subTest(payload=payload), patch.object(
                    server.household_entities, "guest_mode",
                    return_value="input_boolean.guest_mode"), patch.object(
                    server, "build_opener", return_value=Opener(payload)):
                self.assertIsNone(server.read_guest_mode())

    def test_guest_mode_database_failure_returns_unknown(self):
        with patch.object(server.household_entities, "guest_mode",
                          side_effect=sqlite3.OperationalError("database locked")), patch.object(
                          server, "build_opener") as opener:
            self.assertIsNone(server.read_guest_mode())
            opener.assert_not_called()

    def test_guest_mode_valid_state_is_unchanged(self):
        for state in ("on", "off", "unavailable"):
            with self.subTest(state=state), patch.object(
                    server.household_entities, "guest_mode",
                    return_value="input_boolean.guest_mode"), patch.object(
                    server, "build_opener", return_value=Opener({"state": state})):
                self.assertEqual(server.read_guest_mode(), state)

    def test_visitor_presence_non_object_payload_returns_unknown(self):
        payload: object
        for payload in (None, [], "on", 42):
            with self.subTest(payload=payload), patch.object(
                    server.configuration, "get",
                    return_value="input_boolean.visitors"), patch.object(
                    server, "build_opener", return_value=Opener(payload)):
                self.assertIsNone(server.read_visitors_present())

    def test_visitor_presence_on_off_and_unknown(self):
        for state, expected in (("on", True), ("off", False),
                                ("unavailable", None), (None, None)):
            with self.subTest(state=state), patch.object(
                    server.configuration, "get",
                    return_value="input_boolean.visitors"), patch.object(
                    server, "build_opener", return_value=Opener({"state": state})):
                self.assertIs(server.read_visitors_present(), expected)


if __name__ == "__main__":
    unittest.main()
