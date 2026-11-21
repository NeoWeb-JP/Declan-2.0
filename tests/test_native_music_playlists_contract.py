"""Native Spotify playlist Settings route and UI contracts."""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIEW = (ROOT / "custom_components/declan_two/music_playlists_view.py").read_text()
INIT = (ROOT / "custom_components/declan_two/__init__.py").read_text()
JS = (ROOT / "custom_components/declan_two/frontend/panel.js").read_text()


class NativeMusicPlaylistsContractTests(unittest.TestCase):
    def test_playlist_view_is_registered_and_admin_only(self):
        ast.parse(VIEW)
        self.assertIn("DeclanMusicPlaylistsView()", INIT)
        for snippet in (
            'requires_auth = True',
            'not user.is_admin',
            '"/api/settings/music-playlists"',
            'session.post(url, json=body',
            'entry.data["url"] + "/api/settings/music-playlists"',
            '"Cache-Control": "no-store"',
        ):
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, VIEW)

    def test_playlist_operations_and_validation(self):
        for snippet in (
            'set(body) != {"category", "playlist", "operation"}',
            '"add_genre"',
            '"add", "remove", "delete"',
            'body["operation"]',
            'list(payload["categories"])',
            "max_playlists",
        ):
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, VIEW)

    def test_native_settings_ui_uses_safe_dom_and_service(self):
        for snippet in (
            'settings-section--playlists',
            "'GET', 'declan_two/music-playlists'",
            "'POST', 'declan_two/music-playlists'",
            'async loadPlaylists()',
            'async updatePlaylist(operation, playlist, category)',
            "button.dataset.playlistOperation = operation",
            "button.textContent = action",
            "title.textContent = uri",
            "playlists-list",
            "playlists-add-form",
        ):
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, JS)

    def test_single_add_form_and_custom_genre_ui(self):
        self.assertEqual(JS.count('form class="playlists-add-form playlists-global-add"'), 1)
        self.assertEqual(JS.count('form class="playlists-add-form playlists-new-genre"'), 1)
        self.assertIn('async addPlaylistGenre(genre)', JS)
        self.assertIn('genreSelect.replaceChildren()', JS)
        self.assertNotIn("form.closest('details[data-playlist-category]')", JS)


if __name__ == "__main__":
    unittest.main()
