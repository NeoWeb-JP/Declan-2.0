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
    assert 'not self.authorised(request)' in VIEW
    assert '"/api/settings/music-playlists"' in VIEW
    assert 'hass.services.async_call(' in VIEW
    assert 'entry.data["url"] + "/api/settings/music-playlists"' in VIEW
    assert '"Cache-Control": "no-store"' in VIEW


def test_playlist_operations_and_validation():
    assert 'set(body) != {"category", "playlist", "operation"}' in VIEW
    assert '("add", "remove", "delete")' in VIEW
    assert '"add", "remove", "delete"' in VIEW
    assert 'body["operation"]' in VIEW
    assert "CATEGORIES" in VIEW
    assert "max_playlists" in VIEW


def test_native_settings_ui_uses_safe_dom_and_service():
    assert 'settings-section--playlists' in JS
    assert "'GET', 'declan_two/music-playlists'" in JS
    assert "'POST', 'declan_two/music-playlists'" in JS
    assert 'async loadPlaylists()' in JS
    assert 'async updatePlaylist(operation, playlist)' in JS
    assert "button.dataset.playlistOperation = operation" in JS
    assert "button.textContent = label" in JS
    assert "title.textContent = uri" in JS
    assert "playlists-list" in JS
    assert "playlists-add-form" in JS
