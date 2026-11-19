"""Regression tests for extracted AI settings POST handling."""

import sqlite3
from unittest import TestCase
from unittest.mock import Mock

import ai_settings_post


class AISettingsPostTests(TestCase):
    def setUp(self):
        self.handler = Mock()
        self.replace_key = Mock()
        self.save = Mock(return_value={"enabled": True})
        self.configured = Mock(return_value=True)

    def call(self, body):
        ai_settings_post.handle_ai_settings(
            self.handler, body, replace_key=self.replace_key,
            save=self.save, configured=self.configured,
        )

    def test_key_replacement_does_not_return_secret(self):
        self.call({"api_key": "private"})
        self.replace_key.assert_called_once_with("private")
        self.save.assert_not_called()
        self.handler.send_json.assert_called_once_with(200, {"key_configured": True})

    def test_settings_save_reports_key_configuration(self):
        self.call({"settings": {"enabled": True}})
        self.save.assert_called_once_with({"enabled": True})
        self.configured.assert_called_once_with()
        self.handler.send_json.assert_called_once_with(
            200, {"settings": {"enabled": True}, "key_configured": True},
        )

    def test_invalid_payloads_do_not_mutate(self):
        body: object
        for body in (None, [], {}, {"api_key": "x", "settings": {}}, {"unknown": 1}):
            with self.subTest(body=body):
                self.handler.reset_mock()
                self.call(body)
                self.handler.send_json.assert_called_once_with(
                    400, {"error": "Invalid AI settings payload"},
                )
        self.replace_key.assert_not_called()
        self.save.assert_not_called()

    def test_validation_and_storage_failures(self):
        for error, expected in (
            (ValueError("invalid key"), (400, {"error": "invalid key"})),
            (OSError("secret location"), (503, {"error": "Could not save AI settings."})),
            (sqlite3.OperationalError("locked"), (503, {"error": "Could not save AI settings."})),
        ):
            with self.subTest(error=type(error).__name__):
                self.handler.reset_mock()
                self.replace_key.side_effect = error
                self.call({"api_key": "private"})
                self.handler.send_json.assert_called_once_with(*expected)
