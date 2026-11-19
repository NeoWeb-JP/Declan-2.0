"""Media POST routing regression tests."""
import unittest
from types import SimpleNamespace

from declan.music import media_settings_post


class Handler:
    def __init__(self, path):
        self.path = path
        self.calls = []

    def approved_player_settings(self, body):
        self.calls.append(("players", body))

    def spotify_settings(self, body):
        self.calls.append(("spotify", body))


class MediaSettingsPostTests(unittest.TestCase):
    def setUp(self):
        self.music = SimpleNamespace(spotify_credentials=lambda: "credentials")
        self.playlists = SimpleNamespace(start_refresh=lambda: None,
                                         manage=lambda: None)
        self.playlist_calls = []

    def dispatch(self, path, body):
        handler = Handler(path)
        def playlist_handler(*args, **kwargs):
            self.playlist_calls.append((args, kwargs))
        media_settings_post.dispatch(
            handler, body, music=self.music,
            spotify_playlists=self.playlists,
            playlist_handler=playlist_handler,
            opener_factory=lambda: "opener",
        )
        return handler

    def test_exact_route_allowlist(self):
        for path in media_settings_post.ROUTES:
            self.assertTrue(media_settings_post.handles(path))
        for path in ("/api/settings/spotify/other", "/api/settings/ai",
                     "/api/settings/media-players/"):
            self.assertFalse(media_settings_post.handles(path))
            with self.assertRaises(ValueError):
                self.dispatch(path, {})

    def test_media_players(self):
        body = {"area": "kitchen"}
        self.assertEqual(self.dispatch("/api/settings/media-players", body).calls,
                         [("players", body)])

    def test_spotify_settings_validation(self):
        with self.assertRaises(ValueError):
            self.dispatch("/api/settings/spotify", [])
        body = {"client_id": "example"}
        self.assertEqual(self.dispatch("/api/settings/spotify", body).calls,
                         [("spotify", body)])

    def test_playlist_dependencies_and_payload(self):
        body = {"operation": "refresh"}
        self.dispatch("/api/settings/music-playlists", body)
        self.assertEqual(len(self.playlist_calls), 1)
        args, kwargs = self.playlist_calls[0]
        self.assertEqual(args[1], body)
        self.assertIs(kwargs["credentials"], self.music.spotify_credentials)
        self.assertIs(kwargs["start_refresh"], self.playlists.start_refresh)
        self.assertIs(kwargs["manage"], self.playlists.manage)
        self.assertEqual(kwargs["opener_factory"](), "opener")


if __name__ == "__main__":
    unittest.main()
