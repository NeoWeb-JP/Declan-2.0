"""Regression tests for extracted Spotify playlist POST handler."""

from unittest import TestCase
from unittest.mock import Mock

import music_playlists_post


class MusicPlaylistsPostTests(TestCase):
    def setUp(self):
        self.handler = Mock()
        self.credentials = Mock(return_value=(("client", "secret"), None))
        self.refresh = Mock(return_value={"started": True})
        self.manage = Mock(return_value={"playlists": []})
        self.opener = Mock()

    def call(self, body):
        music_playlists_post.handle_music_playlists(
            self.handler, body, credentials=self.credentials,
            start_refresh=self.refresh, manage=self.manage,
            opener_factory=self.opener,
        )

    def test_refresh_with_credentials(self):
        self.call({"category": "Country", "operation": "refresh"})
        self.refresh.assert_called_once()
        self.assertEqual(self.refresh.call_args.args[0], "Country")
        self.assertIs(self.refresh.call_args.args[1], self.opener)
        self.manage.assert_not_called()
        self.handler.send_json.assert_called_once_with(200, {"started": True})

    def test_refresh_without_credentials_is_rejected(self):
        self.credentials.return_value = (("client", ""), None)
        self.call({"category": "Country", "operation": "refresh"})
        self.refresh.assert_not_called()
        self.handler.send_json.assert_called_once_with(
            409, {"error": "Configure Spotify credentials before refreshing playlists."},
        )

    def test_other_operations_delegate_to_manage(self):
        body = {"operation": "list"}
        self.call(body)
        self.manage.assert_called_once_with(body)
        self.credentials.assert_not_called()
        self.handler.send_json.assert_called_once_with(200, {"playlists": []})

    def test_validation_and_storage_errors(self):
        for error, expected in (
            (ValueError("bad category"), (400, {"error": "bad category"})),
            (OSError("private path"), (503, {"error": "Spotify playlist storage unavailable."})),
        ):
            with self.subTest(error=type(error).__name__):
                self.handler.reset_mock()
                self.manage.side_effect = error
                self.call({"operation": "list"})
                self.handler.send_json.assert_called_once_with(*expected)
