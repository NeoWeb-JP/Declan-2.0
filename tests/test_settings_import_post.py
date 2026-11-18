"""Regression tests for extracted settings-import POST handling."""

import sqlite3
from unittest import TestCase
from unittest.mock import Mock

import settings_import_post


class SettingsImportPostTests(TestCase):
    def setUp(self):
        self.handler = Mock()
        self.preview = Mock(return_value={"changes": []})
        self.apply = Mock()

    def call(self, body):
        settings_import_post.handle_settings_import(
            self.handler, body, preview=self.preview, apply=self.apply,
        )

    def test_preview_without_confirmation(self):
        self.call({"document": {"version": 1}})
        self.preview.assert_called_once_with({"version": 1})
        self.apply.assert_not_called()
        self.handler.send_json.assert_called_once_with(200, {"changes": []})

    def test_confirmed_apply_preserves_expected(self):
        self.call({"document": {"version": 1}, "expected": "revision", "confirm": True})
        self.apply.assert_called_once_with({"version": 1}, "revision")
        self.preview.assert_not_called()
        self.handler.send_json.assert_called_once_with(200, {"saved": True})

    def test_rejects_unconfirmed_and_unknown_fields(self):
        for body in (None, [], {"confirm": False}, {"confirm": 1}, {"unknown": True}):
            with self.subTest(body=body):
                self.handler.reset_mock()
                self.call(body)
                self.assertEqual(self.handler.send_json.call_args.args[0], 400)
        self.apply.assert_not_called()
        self.preview.assert_not_called()

    def test_validation_and_storage_errors(self):
        for error, expected in (
            (ValueError("invalid document"), (400, {"error": "invalid document"})),
            (OSError("private path"), (503, {"error": "Settings could not be imported."})),
            (sqlite3.OperationalError("locked"), (503, {"error": "Settings could not be imported."})),
        ):
            with self.subTest(error=type(error).__name__):
                self.handler.reset_mock()
                self.preview.side_effect = error
                self.call({"document": {}})
                self.handler.send_json.assert_called_once_with(*expected)
