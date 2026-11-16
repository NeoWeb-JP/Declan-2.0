"""Native Spotify playlist Settings route and UI contracts."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIEW = (ROOT / "custom_components/declan_two/music_playlists_view.py").read_text()
INIT = (ROOT / "custom_components/declan_two/__init__.py").read_text()
JS = (ROOT / "custom_components/declan_two/frontend/panel.js").read_text()


def test_playlist_view_is_registered_and_admin_only():
    ast.parse(VIEW)
    assert "DeclanMusicPlaylistsView()" in INIT
    assert 'requires_auth = True' in VIEW
    assert 'not user.is_admin' in VIEW
    assert '"/api/settings/music-playlists"' in VIEW
    assert 'session.post(url, json=body' in VIEW
    assert 'entry.data["url"] + "/api/settings/music-playlists"' in VIEW
    assert '"Cache-Control": "no-store"' in VIEW


def test_playlist_operations_and_validation():
    assert 'set(body) != {"category", "playlist", "operation"}' in VIEW
    assert '"add_genre"' in VIEW
    assert '"add", "remove", "delete"' in VIEW
    assert 'body["operation"]' in VIEW
    assert 'list(payload["categories"])' in VIEW
    assert "max_playlists" in VIEW


def test_native_settings_ui_uses_safe_dom_and_service():
    assert 'settings-section--playlists' in JS
    assert "'GET', 'declan_two/music-playlists'" in JS
    assert "'POST', 'declan_two/music-playlists'" in JS
    assert 'async loadPlaylists()' in JS
    assert 'async updatePlaylist(operation, playlist, category)' in JS
    assert "button.dataset.playlistOperation = operation" in JS
    assert "button.textContent = action" in JS
    assert "title.textContent = uri" in JS
    assert "playlists-list" in JS
    assert "playlists-add-form" in JS

def test_single_add_form_and_custom_genre_ui():
    assert JS.count('form class="playlists-add-form playlists-global-add"') == 1
    assert JS.count('form class="playlists-add-form playlists-new-genre"') == 1
    assert 'async addPlaylistGenre(genre)' in JS
    assert 'genreSelect.replaceChildren()' in JS
    assert 'form.closest(\'details[data-playlist-category]\')' not in JS
