"""Regression tests for history intent correction POST adapter."""

import sqlite3
from unittest import TestCase
from unittest.mock import Mock

import history_intents_post


class HistoryIntentsPostTests(TestCase):
    def setUp(self):
        self.handler = Mock()
        self.forget = Mock()
        self.edit = Mock()
        self.teach = Mock()

    def call(self, body):
        history_intents_post.handle_history_intents(
            self.handler, body, forget_intent=self.forget,
            edit_intent=self.edit, teach_intent=self.teach,
            unmatched_reply="unmatched",
        )

    def test_forget_valid_phrase(self):
        self.call({"forget": "old command"})
        self.forget.assert_called_once_with("old command")
        self.handler.send_json.assert_called_once_with(200, {"saved": True})

    def test_edit_preserves_expected_previous(self):
        self.call({"phrase": "lights", "target": "script.lights", "previous": "script.old"})
        self.edit.assert_called_once_with("lights", "script.lights", "script.old")
        self.handler.send_json.assert_called_once_with(200, {"saved": True})

    def test_teach_valid_turn(self):
        self.call({"turn_id": 42, "target": "script.lights"})
        self.teach.assert_called_once_with(42, "script.lights", "unmatched")
        self.handler.send_json.assert_called_once_with(200, {"saved": True})

    def test_rejects_invalid_payloads(self):
        for body in (None, [], {}, {"forget": ""}, {"forget": "x" * 121},
                     {"turn_id": True, "target": "x"}, {"turn_id": 0, "target": "x"},
                     {"turn_id": 2**63, "target": "x"}, {"turn_id": 1, "target": ""}):
            with self.subTest(body=body):
                self.handler.reset_mock()
                self.call(body)
                self.assertEqual(self.handler.send_json.call_args.args[0], 400)
        self.forget.assert_not_called()
        self.edit.assert_not_called()
        self.teach.assert_not_called()

    def test_validation_and_storage_errors(self):
        for error, expected in (
            (ValueError("stale"), (400, {"error": "stale"})),
            (OSError("private path"), (503, {"error": "Intent corrections are unavailable."})),
            (sqlite3.OperationalError("locked"), (503, {"error": "Intent corrections are unavailable."})),
        ):
            with self.subTest(error=type(error).__name__):
                self.handler.reset_mock()
                self.edit.side_effect = error
                self.call({"phrase": "a", "target": "b", "previous": "c"})
                self.handler.send_json.assert_called_once_with(*expected)
