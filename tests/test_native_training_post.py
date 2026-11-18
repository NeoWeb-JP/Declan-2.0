"""Regression tests for native response and intention POST extraction."""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock

import native_training_post as routes


class NativeTrainingPostTests(TestCase):
    def setUp(self):
        self.handler = Mock()
        self.commands = Mock()
        self.routines = Mock()
        self.routines.ENTITY.fullmatch.return_value = True
        self.discovery = Mock(return_value=SimpleNamespace(
            error=None, scripts=[{"entity_id": "script.morning"}],
        ))
        self.connection = Mock(return_value="connection")

    def responses(self, body):
        routes.handle_routine_responses(
            self.handler, body, command_responses=self.commands,
            routine_responses=self.routines, discover=self.discovery,
            connection=self.connection,
        )

    def test_command_snapshot_without_ha_discovery(self):
        self.commands.item.return_value = {"id": "command:lights"}
        self.commands.snapshot.return_value = {"responses": []}
        self.responses({"entity_id": "command:lights"})
        self.discovery.assert_not_called()
        self.handler.send_json.assert_called_once_with(200, {"responses": []})

    def test_routine_save_uses_fresh_discovery(self):
        self.routines.save.return_value = {"saved": True}
        self.responses({"entity_id": "script.morning", "profile": "Home", "expected": []})
        self.discovery.assert_called_once_with("connection", fresh=True)
        self.routines.save.assert_called_once_with(
            {"entity_id": "script.morning"}, "Home", [],
        )
        self.handler.send_json.assert_called_once_with(200, {"saved": True})

    def test_routine_discovery_unavailable(self):
        self.discovery.return_value = SimpleNamespace(error="offline", scripts=[])
        self.responses({"entity_id": "script.morning"})
        self.handler.send_json.assert_called_once_with(
            503, {"error": "Home Assistant routines unavailable. Try again."},
        )

    def test_invalid_response_change(self):
        self.responses({"entity_id": "script.morning", "unexpected": 1})
        self.handler.send_json.assert_called_once_with(
            400, {"error": "Invalid response change"},
        )

    def test_native_intent_edit_and_forget(self):
        history = Mock()
        pipeline = Mock()
        routes.handle_native_intents(
            self.handler, {"phrase": "on", "target": "lights", "previous": "old"},
            history=history, voicepipeline=pipeline, unmatched_reply="unknown",
        )
        history.edit_intent.assert_called_once_with("on", "lights", "old")
        history.learned_intent.return_value = "lights"
        routes.handle_native_intents(
            self.handler, {"forget": "on", "previous": "lights"},
            history=history, voicepipeline=pipeline, unmatched_reply="unknown",
        )
        history.forget_intent.assert_called_once_with("on")

    def test_stale_intent_rejected(self):
        history = Mock()
        history.learned_intent.return_value = "changed"
        routes.handle_native_intents(
            self.handler, {"forget": "on", "previous": "old"},
            history=history, voicepipeline=Mock(), unmatched_reply="unknown",
        )
        self.handler.send_json.assert_called_once_with(
            400, {"error": "Intention changed. Refresh before forgetting."},
        )

    def test_recording_teaches_only_reviewable_transcript(self):
        history = Mock()
        pipeline = Mock()
        pipeline.identifier.return_value = "recording"
        pipeline.interactions.side_effect = [
            [{"id": "recording", "transcript": "turn on light", "status": "confirmed"}], [],
        ]
        pipeline.InteractionReviewResult.parse.return_value.blocks_teaching = False
        routes.handle_native_intents(
            self.handler, {"recording_id": "recording", "target": "light.on"},
            history=history, voicepipeline=pipeline, unmatched_reply="unknown",
        )
        history.teach_phrase.assert_called_once_with("turn on light", "light.on")
        self.handler.send_json.assert_called_once_with(200, {"saved": True})

    def test_turn_id_teaches_with_unmatched_reply(self):
        history = Mock()
        routes.handle_native_intents(
            self.handler, {"turn_id": 7, "target": "light.on"},
            history=history, voicepipeline=Mock(), unmatched_reply="unknown",
        )
        history.teach_intent.assert_called_once_with(7, "light.on", "unknown")
