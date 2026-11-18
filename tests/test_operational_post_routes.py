"""Regression tests for batched operational POST adapters."""

import sqlite3
import subprocess
from unittest import TestCase
from unittest.mock import Mock

import operational_post_routes as routes


class OperationalPostRoutesTests(TestCase):
    def setUp(self):
        self.handler = Mock()

    def test_update_check(self):
        status = Mock()
        status.to_wire.return_value = {"status": "idle"}
        check = Mock(return_value=["1.0"])
        queue = Mock()
        routes.handle_updates(
            self.handler, {"operation": "check", "include_prereleases": True},
            check=check, status_result=Mock(return_value=status),
            prerelease_versions=Mock(return_value=["1.1rc"]), queue=queue,
            release_version="0.9",
        )
        check.assert_called_once_with(True)
        queue.assert_not_called()
        self.handler.send_json.assert_called_once_with(
            200, {"status": "idle", "current": "0.9",
                  "versions": ["1.0"], "prereleases": ["1.1rc"]},
        )

    def test_update_queue_and_errors(self):
        queue = Mock()
        def call(body):
            routes.handle_updates(
                self.handler, body, check=Mock(), status_result=Mock(),
                prerelease_versions=Mock(), queue=queue, release_version="1.0",
            )
        call({"version": "1.1", "include_prereleases": True})
        queue.assert_called_once_with("1.1", "1.0", True)
        self.handler.send_json.assert_called_once_with(202, {"status": "installing"})
        for error, status in ((ValueError("conflict"), 409),
                              (OSError("network"), 503),
                              (subprocess.SubprocessError("failed"), 503)):
            with self.subTest(error=type(error).__name__):
                self.handler.reset_mock()
                queue.side_effect = error
                call({})
                self.assertEqual(self.handler.send_json.call_args.args[0], status)

    def test_spotify_credentials_require_confirmation(self):
        save = Mock()
        for body in (None, {}, {"client_id": "a", "client_secret": "b", "confirm": 1},
                     {"client_id": "a", "client_secret": "b", "confirm": False}):
            with self.subTest(body=body):
                self.handler.reset_mock()
                routes.handle_spotify_credentials(self.handler, body, save=save)
                self.handler.send_json.assert_called_once_with(
                    400, {"error": "Explicit confirmation and both credentials required."},
                )
        save.assert_not_called()
        valid = {"client_id": "a", "client_secret": "b", "confirm": True}
        routes.handle_spotify_credentials(self.handler, valid, save=save)
        save.assert_called_once_with(valid)

    def test_assist_history_saves_typed_steps(self):
        record = Mock()
        steps = Mock(return_value=["step"])
        token = Mock(return_value="generated")
        routes.handle_assist_history(
            self.handler, {"reply": "Done", "outcome": "ok",
                           "routine_status": "success", "steps": [{"id": 1}]},
            message="lights", session_id="", record=record,
            token_urlsafe=token, action_results=steps,
        )
        token.assert_called_once_with(24)
        steps.assert_called_once_with([{"id": 1}])
        record.assert_called_once_with(
            "generated", "ha_sentence", "lights", "Done", "ok", "success", ["step"],
        )
        self.handler.send_json.assert_called_once_with(200, {"history_saved": True})

    def test_assist_history_validation_and_storage_error(self):
        record = Mock()
        steps = Mock(return_value=[])
        token = Mock(return_value="generated")
        def call(body):
            routes.handle_assist_history(
                self.handler, body, message="hello", session_id="session",
                record=record, token_urlsafe=token, action_results=steps,
            )
        for reply in ("", " ", "x" * 1001, None):
            with self.subTest(reply=reply):
                self.handler.reset_mock()
                call({"reply": reply})
                self.assertEqual(self.handler.send_json.call_args.args[0], 400)
        record.assert_not_called()
        for error in (OSError("private path"), sqlite3.OperationalError("locked")):
            with self.subTest(error=type(error).__name__):
                self.handler.reset_mock()
                record.side_effect = error
                call({"reply": "Done"})
                self.handler.send_json.assert_called_once_with(
                    503, {"error": "Conversation history is unavailable."},
                )
