"""Settings and training POST dispatch must remain ordered and exclusive."""

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from declan.http import post_body_routing


def dependencies():
    names = (
        "spotify_save ai_replace_key ai_save ai_configured music spotify_playlists "
        "playlist_handler opener_factory voice_manage pipeline_error profiles_manage "
        "preview apply command_responses routine_responses discover connection history "
        "voicepipeline unmatched_reply forget_intent edit_intent teach_intent storage_errors"
    ).split()
    return {name: MagicMock(name=name) for name in names}


class PostBodyRoutingTests(unittest.TestCase):
    def test_settings_route_takes_precedence_over_training(self):
        handler = SimpleNamespace(path="/api/settings")
        deps = dependencies()
        with patch.object(post_body_routing.settings_voice_post, "handles", return_value=True), \
             patch.object(post_body_routing.settings_voice_post, "dispatch") as settings, \
             patch.object(post_body_routing.training_history_post, "handles") as training:
            self.assertTrue(post_body_routing.dispatch(handler, {}, **deps))
        settings.assert_called_once()
        training.assert_not_called()

    def test_training_route_is_dispatched_when_settings_does_not_match(self):
        handler = SimpleNamespace(path="/api/history/teach")
        deps = dependencies()
        with patch.object(post_body_routing.settings_voice_post, "handles", return_value=False), \
             patch.object(post_body_routing.training_history_post, "handles", return_value=True), \
             patch.object(post_body_routing.training_history_post, "dispatch") as training:
            self.assertTrue(post_body_routing.dispatch(handler, {}, **deps))
        training.assert_called_once()
        self.assertIs(training.call_args.kwargs["history"], deps["history"])
        self.assertIs(training.call_args.kwargs["teach_intent"], deps["teach_intent"])

    def test_unhandled_route_is_not_consumed(self):
        handler = SimpleNamespace(path="/api/chat")
        deps = dependencies()
        with patch.object(post_body_routing.settings_voice_post, "handles", return_value=False), \
             patch.object(post_body_routing.training_history_post, "handles", return_value=False), \
             patch.object(post_body_routing.settings_voice_post, "dispatch") as settings, \
             patch.object(post_body_routing.training_history_post, "dispatch") as training:
            self.assertFalse(post_body_routing.dispatch(handler, {}, **deps))
        settings.assert_not_called()
        training.assert_not_called()

    def test_settings_route_preserves_dependencies(self):
        handler = SimpleNamespace(path="/api/settings")
        deps = dependencies()
        with patch.object(post_body_routing.settings_voice_post, "handles", return_value=True), \
             patch.object(post_body_routing.settings_voice_post, "dispatch") as settings:
            self.assertTrue(post_body_routing.dispatch(handler, {"rooms": []}, **deps))
        self.assertIs(settings.call_args.kwargs["spotify_save"], deps["spotify_save"])
        self.assertIs(settings.call_args.kwargs["opener_factory"], deps["opener_factory"])
        self.assertIs(settings.call_args.kwargs["voice_manage"], deps["voice_manage"])


if __name__ == "__main__":
    unittest.main()
