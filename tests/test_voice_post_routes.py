"""Regression tests for extracted voice-management HTTP response adapters."""

import sqlite3
from unittest import TestCase
from unittest.mock import Mock

import voice_post_routes


class PipelineError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class VoicePostRouteTests(TestCase):
    def setUp(self):
        self.handler = Mock()

    def test_voicepipeline_success_and_validation_failure(self):
        manage = Mock(return_value={"saved": True})
        voice_post_routes.handle_voicepipeline(
            self.handler, {"operation": "resolve"},
            manage=manage, pipeline_error=PipelineError,
        )
        manage.assert_called_once_with({"operation": "resolve"})
        self.handler.send_json.assert_called_once_with(200, {"saved": True})
        self.handler.reset_mock()
        voice_post_routes.handle_voicepipeline(
            self.handler, {}, manage=Mock(side_effect=ValueError("invalid")),
            pipeline_error=PipelineError,
        )
        self.handler.send_json.assert_called_once_with(400, {"error": "invalid"})

    def test_voicepipeline_provider_error_preserves_status(self):
        voice_post_routes.handle_voicepipeline(
            self.handler, {}, manage=Mock(side_effect=PipelineError(409, "conflict")),
            pipeline_error=PipelineError,
        )
        self.handler.send_json.assert_called_once_with(409, {"error": "conflict"})

    def test_voice_profile_retired_enrolment_is_blocked(self):
        manage = Mock()
        for operation in ("create", "save_sample"):
            with self.subTest(operation=operation):
                self.handler.reset_mock()
                voice_post_routes.handle_voice_profiles(
                    self.handler, {"operation": operation}, manage=manage,
                )
                self.assertEqual(self.handler.send_json.call_args.args[0], 400)
        manage.assert_not_called()

    def test_voice_profile_success_and_storage_error(self):
        manage = Mock(return_value={"profiles": []})
        voice_post_routes.handle_voice_profiles(
            self.handler, {"operation": "list"}, manage=manage,
        )
        self.handler.send_json.assert_called_once_with(200, {"profiles": []})
        for failure in (OSError("unavailable"), sqlite3.OperationalError("locked")):
            with self.subTest(failure=type(failure).__name__):
                self.handler.reset_mock()
                voice_post_routes.handle_voice_profiles(
                    self.handler, {}, manage=Mock(side_effect=failure),
                )
                self.handler.send_json.assert_called_once_with(
                    503, {"error": "Voice profiles could not be saved."},
                )
