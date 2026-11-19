"""Regression tests for history-clear POST adapter."""

import sqlite3
from unittest import TestCase
from unittest.mock import Mock

from declan.http import history_post_routes


class HistoryClearTests(TestCase):
    def setUp(self):
        self.handler = Mock()

    def call(self, body, clear):
        history_post_routes.handle_history_clear(
            self.handler, body, clear=clear,
            storage_errors=(OSError, sqlite3.Error),
        )

    def test_requires_explicit_confirmation(self):
        clear = Mock()
        body: object
        for body in (None, [], {}, {"confirm": False}, {"confirm": 1}):
            with self.subTest(body=body):
                self.handler.reset_mock()
                self.call(body, clear)
                self.handler.send_json.assert_called_once_with(
                    400, {"error": "Confirm before clearing conversation history."},
                )
        clear.assert_not_called()

    def test_success_preserves_deleted_count(self):
        clear = Mock(return_value=7)
        self.call({"confirm": True}, clear)
        clear.assert_called_once_with()
        self.handler.send_json.assert_called_once_with(200, {"deleted": 7})

    def test_storage_errors_are_not_leaked(self):
        for error in (OSError("private path"), sqlite3.OperationalError("locked")):
            with self.subTest(error=type(error).__name__):
                self.handler.reset_mock()
                self.call({"confirm": True}, Mock(side_effect=error))
                self.handler.send_json.assert_called_once_with(
                    503, {"error": "Conversation history could not be cleared."},
                )
