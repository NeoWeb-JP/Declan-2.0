"""Settings/voice POST dispatch regression coverage."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import settings_voice_post as routes


class SettingsVoicePostTests(unittest.TestCase):
    def setUp(self):
        self.handler = SimpleNamespace(path="")
        self.body = {"action": "test"}
        self.kwargs = dict(
            spotify_save=lambda: None, ai_replace_key=lambda: None,
            ai_save=lambda: None, ai_configured=lambda: None,
            music=object(), spotify_playlists=object(),
            playlist_handler=lambda: None, opener_factory=lambda: None,
            voice_manage=lambda: None, pipeline_error=ValueError,
            profiles_manage=lambda: None, preview=lambda: None,
            apply=lambda: None,
        )

    def test_known_routes_and_unknown_rejection(self):
        for path in routes.ROUTES:
            self.assertTrue(routes.handles(path), path)
        self.assertFalse(routes.handles("/api/assist"))
        self.handler.path = "/api/assist"
        with self.assertRaises(ValueError):
            routes.dispatch(self.handler, self.body, **self.kwargs)

    def test_route_delegation(self):
        cases = (
            ("/api/native/spotify-credentials", routes.operational_post_routes, "handle_spotify_credentials"),
            ("/api/settings/ai", routes.ai_settings_post, "handle_ai_settings"),
            ("/api/voicepipeline", routes.voice_post_routes, "handle_voicepipeline"),
            ("/api/voice-profiles", routes.voice_post_routes, "handle_voice_profiles"),
            ("/api/settings/import", routes.settings_import_post, "handle_settings_import"),
            ("/api/native/settings-import", routes.settings_import_post, "handle_settings_import"),
        )
        for path, module, method in cases:
            with self.subTest(path=path), patch.object(module, method) as delegate:
                self.handler.path = path
                routes.dispatch(self.handler, self.body, **self.kwargs)
                delegate.assert_called_once()
                self.assertIs(delegate.call_args.args[0], self.handler)
                self.assertIs(delegate.call_args.args[1], self.body)

    def test_media_route_delegation(self):
        self.handler.path = "/api/test-media"
        with patch.object(routes.media_settings_post, "handles", return_value=True), patch.object(
            routes.media_settings_post, "dispatch",
        ) as delegate:
            self.assertTrue(routes.handles(self.handler.path))
            routes.dispatch(self.handler, self.body, **self.kwargs)
            delegate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
