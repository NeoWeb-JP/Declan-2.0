"""Regression coverage for approved per-area media player routing."""
import json
import approved_media_players as approved
import music
import pytest


def test_only_approved_players_are_selected(tmp_path, monkeypatch):
    path = tmp_path / "players.json"
    monkeypatch.setenv("DECLAN_APPROVED_MEDIA_PLAYERS_FILE", str(path))
    approved.save({"Kitchen": "media_player.kitchen_declan_voice_assistant",
                   "everywhere": "media_player.everywhere_2"})
    inventory = [
        {"entity_id": "media_player.kitchen_declan_voice_assistant",
         "state": "playing", "declan_music_assistant": True},
        {"entity_id": "media_player.kitchen_sonos",
         "state": "playing", "declan_music_assistant": True},
        {"entity_id": "media_player.everywhere_2",
         "state": "idle", "declan_music_assistant": True},
    ]
    destinations, players = music.music_players(inventory)
    assert destinations == {"kitchen": "media_player.kitchen_declan_voice_assistant",
                            "everywhere": "media_player.everywhere_2"}
    assert "media_player.kitchen_sonos" not in players


def test_missing_or_non_music_assistant_player_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("DECLAN_APPROVED_MEDIA_PLAYERS_FILE", str(tmp_path / "players.json"))
    approved.save({"kitchen": "media_player.kitchen_sonos", "study": "media_player.missing"})
    destinations, players = music.music_players([
        {"entity_id": "media_player.kitchen_sonos", "state": "playing",
         "declan_music_assistant": False}])
    assert destinations == {"kitchen": None, "study": None}
    assert players == {}


def test_invalid_mapping_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("DECLAN_APPROVED_MEDIA_PLAYERS_FILE", str(tmp_path / "players.json"))
    with pytest.raises(ValueError):
        approved.save({"kitchen": "switch.kitchen"})
    with pytest.raises(ValueError):
        approved.save({"kitchen": "media_player.kitchen;bad"})


def test_playback_control_does_not_use_unapproved_player(tmp_path, monkeypatch):
    monkeypatch.setenv("DECLAN_APPROVED_MEDIA_PLAYERS_FILE", str(tmp_path / "players.json"))
    approved.save({"kitchen": "media_player.kitchen_declan_voice_assistant"})
    inventory = [
        {"entity_id": "media_player.kitchen_declan_voice_assistant", "state": "idle",
         "declan_music_assistant": True, "attributes": {}},
        {"entity_id": "media_player.kitchen_sonos", "state": "playing",
         "declan_music_assistant": True, "attributes": {}},
    ]
    calls = []
    monkeypatch.setattr(music, "request", lambda *args, **kwargs: calls.append(args))
    reply, outcome = music.control(("media_next_track", "kitchen"), object(),
                                   lambda connection: (inventory, None))
    assert outcome == "unavailable"
    assert not calls
