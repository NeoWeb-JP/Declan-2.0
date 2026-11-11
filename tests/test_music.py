"""Check Spotify handoffs without changing live playback."""

import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

import music
import server


class MusicTests(unittest.TestCase):
    def setUp(self):
        self.players = {entity: {"entity_id": entity, "state": "idle", "attributes": {}}
                        for entity in music.PLAYERS.values()}
        self.bedroom, self.kitchen, self.group = (music.PLAYERS[room] for room in ("bedroom", "kitchen", "everywhere"))
        self.track = {"media_content_id": "spotify--account://track/0JkIre0YxNmKGMU5V7ZiDx",
                      "media_title": "Coward of the County", "media_artist": "Kenny Rogers"}
        self.players[self.bedroom].update(state="playing", attributes=self.track)
        self.calls = []
        self.searches = []
        self.search_results = None
        self.spotify_tokens = 0
        self.spotify_throttled = False
        self.stop_works = True
        self.throttled = False
        self.play_response = None
        self.enterContext(patch.dict(music.os.environ, {
            "DECLAN_SPOTIFY_PRESETS": "{}", "DECLAN_SPOTIFY_CLIENT_ID": "test-client",
            "DECLAN_SPOTIFY_CLIENT_SECRET": "test-secret",
        }))
        self.enterContext(patch.object(music, "spotify_token", None))
        folder = self.enterContext(TemporaryDirectory())
        self.enterContext(patch.object(music, "SPOTIFY_SETTINGS", Path(folder) / "spotify-settings.json"))
        self.enterContext(patch.object(music, "PREFERENCES", Path(folder) / "music-preferences.sqlite3"))
        self.enterContext(patch.object(music, "recent_blacklist_skips", {}))
        self.enterContext(patch.object(music, "sleep"))

    def open(self, request, timeout):
        if request.full_url == "https://accounts.spotify.com/api/token":
            self.spotify_tokens += 1
            credentials = parse_qs(request.data.decode())
            self.assertIn(credentials["client_id"][0], {"test-client", "new-client"})
            return io.BytesIO(b'{"access_token":"test-token","expires_in":3600}')
        if request.full_url.startswith("https://api.spotify.com/v1/search?"):
            self.assertEqual(request.get_header("Authorization"), "Bearer test-token")
            query = parse_qs(urlsplit(request.full_url).query)
            types = query["type"][0].split(",")
            term = query["q"][0]
            self.searches.append({"media_type": types, "q": term})
            if self.spotify_throttled:
                raise HTTPError(request.full_url, 429, "Too Many Requests", {}, None)
            result = self.search_results
            if result is None:
                result = {"tracks": [{"name": term, "id": "0123456789AbCdEfGhIjKl"}]}
            payload = {key: {"items": [
                {"name": item["name"], "id": item.get("id", "0123456789AbCdEfGhIjKl")} for item in items
            ]} for key, items in result.items()}
            return io.BytesIO(json.dumps(payload).encode())
        path = request.full_url.removeprefix("http://ha")
        if request.data is None:
            return io.BytesIO(json.dumps(self.players[path.rsplit("/", 1)[1]]).encode())
        data = json.loads(request.data)
        if path == "/api/template":
            return io.BytesIO(b"music-assistant-entry")
        if path.endswith("/search?return_response"):
            self.searches.append(data)
            result = self.search_results
            if result is None:
                result = {"tracks": [{"name": data["name"], "uri": "spotify://track/selected"}]}
            return io.BytesIO(json.dumps({"service_response": result}).encode())
        self.calls.append((path.rsplit("/", 1)[1], data))
        player = self.players[data["entity_id"]]
        if path.endswith("/media_stop"):
            if self.stop_works:
                player["state"] = "idle"
        elif path.endswith("/media_pause"):
            player["state"] = "paused"
        elif path.endswith(("/media_next_track", "/media_previous_track")):
            player["attributes"] = {**self.track, "media_content_id": path.rsplit("/", 1)[1]}
        elif path.endswith("/transfer_queue"):
            source = self.players[data["source_player"]]
            player.update(state="playing", attributes=source["attributes"])
            source["state"] = "idle"
        elif path.endswith("/media_play"):
            player["state"] = "playing"
        elif self.throttled:
            raise HTTPError(request.full_url, 429, "Too Many Requests", {}, None)
        elif self.play_response:
            self.play_response(player, data)
        else:
            player.update(state="playing", attributes={**self.track, "media_content_id": data["media_id"]})
        return io.BytesIO(b"[]")

    def play(self, phrase):
        return music.play(music.parse(phrase), ("http://ha", {}, self), lambda _: (list(self.players.values()), None))

    def control(self, phrase, **kwargs):
        return music.control(music.parse_control(phrase), ("http://ha", {}, self),
                             lambda _: (list(self.players.values()), None), **kwargs)

    def test_unqualified_music_uses_satellite_area_and_spotify_search(self):
        utility = "media_player.utility_queue"
        satellite = "assist_satellite.utility"
        self.players[utility] = {"entity_id": utility, "state": "idle", "attributes": {},
                                 "declan_area": "Utility Room", "declan_music_assistant": True}
        self.players[satellite] = {"entity_id": satellite, "state": "idle",
                                  "declan_device": "utility-device", "declan_area": "Utility Room"}
        self.players[self.bedroom]["state"] = "idle"
        self.search_results = {"playlists": [{"name": "Country Music", "id": "A" * 22}]}
        for origin in (satellite, "utility-device"):
            with self.subTest(origin=origin):
                reply, outcome = music.play(music.parse("play country music"), ("http://ha", {}, self),
                                            lambda _: (list(self.players.values()), None), origin=origin)
                self.assertEqual(outcome, "confirmed", reply)
                self.assertEqual(self.calls[-1][1]["entity_id"], utility)
                self.assertEqual(self.searches[-1]["q"], "country music")

    def test_unqualified_music_without_origin_asks_for_room_without_playback(self):
        reply, outcome = self.play("play country music")
        self.assertEqual((reply, outcome), ("Which room should I play the music in?", "unresolved"))
        self.assertEqual(self.calls, [])
        self.assertEqual(self.searches, [])

    def test_registry_area_mapping_follows_renamed_music_assistant_entities(self):
        self.players[self.bedroom]["declan_music_assistant"] = False
        replacement = "media_player.new_bedroom_queue"
        self.players[replacement] = {
            "entity_id": replacement, "state": "idle", "attributes": {},
            "declan_area": "Master Bedroom", "declan_music_assistant": True,
        }
        self.assertEqual(self.play("play coward of the county in the bedroom")[1], "confirmed")
        self.assertEqual(self.calls[-1][1]["entity_id"], replacement)
        self.players[replacement]["declan_area"] = "Study"
        self.assertEqual(self.play("play coward of the county in the study")[1], "confirmed")
        self.assertEqual(self.calls[-1][1]["entity_id"], replacement)
        self.assertEqual(self.play("play coward of the county in the bedroom")[1], "unresolved")

    def test_two_registered_players_in_one_area_require_clarification(self):
        for entity in (self.bedroom, self.kitchen):
            self.players[entity].update(declan_area="Bedroom", declan_music_assistant=True)
        self.assertEqual(self.play("play country music in the bedroom")[1], "unresolved")
        self.assertEqual(self.control("next song", origin="new-satellite", assist=True,
                                      read_areas=lambda *args: {"Master Bedroom": []})[1], "unresolved")
        self.assertEqual(self.calls, [])

    def test_everywhere_uses_unique_available_replacement(self):
        replacement = "media_player.everywhere_3"
        self.players[self.group]["state"] = "unavailable"
        self.players[replacement] = {"entity_id": replacement, "state": "idle",
                                     "attributes": {"friendly_name": "Everywhere"}}
        self.assertEqual(self.play("play music everywhere")[1], "confirmed")
        self.assertEqual(self.calls[-1], ("transfer_queue", {
            "entity_id": replacement, "source_player": self.bedroom, "auto_play": True,
        }))
        self.players[replacement]["attributes"] = {**self.track, "friendly_name": "Everywhere"}
        self.assertEqual(self.control("pause music everywhere")[1], "confirmed")

    def test_assist_skip_retries_inventory_then_controls_everywhere(self):
        self.players[self.group].update(state="playing", attributes={**self.track, "group_members": [self.bedroom]})
        with patch.object(music, "music_players", wraps=music.music_players) as resolve:
            responses = iter([(None, "unavailable"), (list(self.players.values()), None)])
            reply, outcome = music.control(music.parse_control("next song"), ("http://ha", {}, self),
                                           lambda _: next(responses), assist=True, origin="satellite",
                                           read_areas=lambda *_: {"bedroom": set()})
            self.assertEqual(outcome, "confirmed", reply)
            resolve.assert_called_once()
        self.assertEqual(self.calls, [("media_next_track", {"entity_id": self.group})])

    def test_dislike_phrases_skip_without_blocking(self):
        for phrase in ("i do not like this song", "i don't like this song", "i don't like this song"):
            self.assertEqual(music.parse_control(phrase), ("media_next_track", None))
        self.assertEqual(self.control("i don't like this song")[1], "confirmed")
        self.assertFalse(music.PREFERENCES.exists())

    def test_feedback_saves_favourites_and_skips_blocked_tracks(self):
        connection = ("http://ha", {}, self)

        def inventory(_):
            return list(self.players.values()), None

        for phrase in ("we like this song", "never play this song again"):
            self.assertEqual(music.feedback(music.parse_feedback(phrase), connection, inventory)[1], "music_feedback")
            if phrase == "we like this song":
                self.assertEqual(music.search_media(connection, self.bedroom, "my favourites", "", "spotify")[1], "track")
        self.assertIsNone(music.search_media(connection, self.bedroom, "my favourites", "", "spotify"))
        music.skip_blocked_tracks(connection, inventory)
        self.assertEqual(self.calls[-1], ("media_next_track", {"entity_id": self.bedroom}))

    def test_routine_playlists_use_saved_links_when_search_is_unconfigured(self):
        with patch.dict(music.os.environ, {"DECLAN_SPOTIFY_CLIENT_ID": "", "DECLAN_SPOTIFY_CLIENT_SECRET": ""}):
            for room, title, playlist_id in (
                ("kitchen", "romantic dinner music", "37i9dQZF1DXbm6HfkbMtFZ"),
                ("bedroom", "sexy time music", "0mQbGXAlmsI3T2Vyfa0IVd"),
            ):
                with self.subTest(title=title):
                    self.calls.clear()
                    self.players[self.kitchen].update(state="idle", attributes={})
                    self.players[self.bedroom].update(state="playing", attributes=self.track)
                    music.play((room, title, "spotify"), ("http://ha", {}, self), lambda _: (list(self.players.values()), None))
                    self.assertEqual([action for action, _ in self.calls], ["media_stop", "play_media"])
                    self.assertEqual(self.calls[-1][1]["media_id"], "https://open.spotify.com/playlist/" + playlist_id)
                    self.assertEqual(self.calls[-1][1]["entity_id"], music.PLAYERS[room])
            self.assertEqual(self.spotify_tokens, 0)

    def test_dinner_uses_spotify_search_then_stops_before_music_assistant_play(self):
        self.search_results = {"playlists": [{"name": "Romantic Dinner", "id": "0123456789AbCdEfGhIjKl"}]}
        reply, outcome = self.play("play romantic dinner music in the kitchen")
        self.assertEqual(outcome, "confirmed", reply)
        self.assertEqual(self.spotify_tokens, 1)
        self.assertEqual(self.searches, [{"media_type": ["playlist"], "q": "romantic dinner music"}])
        self.assertEqual([action for action, _ in self.calls], ["media_stop", "play_media"])
        self.assertEqual(self.calls[-1][1]["entity_id"], self.kitchen)
        self.assertEqual(self.calls[-1][1]["media_id"], "https://open.spotify.com/playlist/0123456789AbCdEfGhIjKl")

    def test_genre_requests_avoid_the_previous_playlist(self):
        self.search_results = {"playlists": [
            {"name": "Country One", "id": "A" * 22}, {"name": "Country Two", "id": "B" * 22},
        ]}
        self.assertEqual(self.play("play country music in the kitchen")[1], "confirmed")
        first = self.calls[-1][1]["media_id"]
        self.assertEqual(self.play("play country music in the kitchen")[1], "confirmed")
        self.assertNotEqual(self.calls[-1][1]["media_id"], first)

    def test_room_music_controls_pause_resume_skip_previous_and_stop(self):
        for phrase, action in (
            ("pause the music in the bedroom", "media_pause"),
            ("continue playing in the bedroom", "media_play"),
            ("skip this song in the bedroom", "media_next_track"),
            ("play the previous track in the bedroom", "media_previous_track"),
            ("stop music in the bedroom", "media_stop"),
        ):
            with self.subTest(phrase=phrase):
                reply, outcome = self.control(phrase)
                self.assertEqual(outcome, "confirmed", reply)
                self.assertEqual(self.calls[-1], (action, {"entity_id": self.bedroom}))

    def test_unqualified_assist_stop_only_controls_the_originating_room(self):
        areas = lambda connection, origin: {"master bedroom": set(), "bedroom": set()}
        self.players[self.kitchen].update(state="playing", attributes=self.track)
        self.assertEqual(self.control("stop", origin="satellite", read_areas=areas, assist=True)[1], "confirmed")
        self.assertEqual(self.calls, [("media_stop", {"entity_id": self.bedroom})])
        self.assertEqual(self.players[self.kitchen]["state"], "playing")

    def test_assist_pause_confirms_a_late_state_update_without_resending(self):
        original_open = self.open
        for timed_out in (False, True):
            with self.subTest(timed_out=timed_out):
                self.players[self.bedroom]["state"] = "playing"
                self.calls.clear()
                reads = 0

                def delayed_pause(request, timeout):
                    nonlocal reads
                    if request.full_url.endswith("/media_pause"):
                        response = original_open(request, timeout)
                        self.players[self.bedroom]["state"] = "playing"
                        if timed_out:
                            raise TimeoutError
                        return response
                    if request.data is None and request.full_url.endswith(self.bedroom):
                        reads += 1
                        if reads == 6:
                            self.players[self.bedroom]["state"] = "paused"
                    return original_open(request, timeout)

                with patch.object(self, "open", side_effect=delayed_pause):
                    reply, outcome = self.control("pause music in the bedroom", assist=True)
                self.assertEqual((reply, outcome), ("Paused playback in the bedroom.", "confirmed"))
                self.assertEqual(self.calls, [("media_pause", {"entity_id": self.bedroom})])

    def test_pause_returns_within_its_budget_when_player_never_reports_paused(self):
        now = 100
        original_open = self.open

        def advance(seconds):
            nonlocal now
            now += seconds

        def slow_player(request, timeout):
            if request.full_url.endswith("/media_pause"):
                original_open(request, timeout)
                self.players[self.bedroom]["state"] = "playing"
                advance(timeout)
                raise TimeoutError
            advance(timeout)
            return original_open(request, timeout)

        with patch.object(self, "open", side_effect=slow_player), patch.object(
            music, "monotonic", side_effect=lambda: now
        ), patch.object(music, "sleep", side_effect=advance):
            reply, outcome = self.control("pause music in the bedroom", assist=True)
        self.assertEqual(outcome, "unverified")
        self.assertIn("took too long", reply)
        self.assertLessEqual(now, 105)
        self.assertEqual(self.calls, [("media_pause", {"entity_id": self.bedroom})])

    def test_ambiguous_or_grouped_room_commands_do_not_stop_other_outputs(self):
        self.players[self.kitchen].update(state="playing", attributes=self.track)
        self.assertEqual(self.control("stop")[1], "unresolved")
        self.players[self.group].update(state="playing", attributes={"group_members": [self.bedroom, self.kitchen]})
        self.assertEqual(self.control("stop music in the bedroom")[1], "unresolved")
        self.assertEqual(self.calls, [])
        self.assertEqual(self.control("stop music everywhere")[1], "confirmed")
        self.assertEqual(self.calls, [("media_stop", {"entity_id": self.group})])

    def test_same_track_moves_without_searching_then_moves_everywhere(self):
        self.assertEqual(self.play("play coward of the county by kenny rogers in the kitchen")[1], "confirmed")
        self.assertEqual(self.play("play music everywhere on spotify")[1], "confirmed")
        self.assertEqual(self.calls, [
            ("transfer_queue", {"entity_id": self.kitchen, "source_player": self.bedroom, "auto_play": True}),
            ("transfer_queue", {"entity_id": self.group, "source_player": self.kitchen, "auto_play": True}),
        ])
        self.assertEqual(self.searches, [])

    def test_new_track_waits_for_stop_and_never_retries_rate_limit(self):
        self.stop_works = False
        self.assertIn("didn't start", self.play("play islands in the stream in the kitchen")[0])
        self.assertEqual([action for action, _ in self.calls], ["media_stop"])
        self.calls.clear()
        self.stop_works = True
        self.throttled = True
        self.assertIn("rate limited", self.play("play islands in the stream in the kitchen")[0])
        self.assertEqual([action for action, _ in self.calls], ["media_stop", "play_media"])

    def test_radio_is_left_alone_and_group_is_a_single_queue(self):
        self.players[self.bedroom]["attributes"] = {"media_content_id": "tunein://station/example"}
        self.assertEqual(self.play("play islands in the stream in the kitchen")[1], "confirmed")
        self.assertEqual([action for action, _ in self.calls], ["play_media"])
        self.players[self.group].update(state="playing", attributes={
            **self.players[self.kitchen]["attributes"], "group_members": [self.kitchen],
        })
        self.assertEqual(self.play("move the music to the bedroom")[1], "confirmed")
        self.assertEqual(self.calls[-1][1]["source_player"], self.group)

    def test_new_track_reports_stopping_the_previous_stream_and_starting_the_request(self):
        reply, outcome = self.play("play islands in the stream in the kitchen")
        self.assertEqual(outcome, "confirmed")
        self.assertIn("stopped the previous Spotify stream and started islands in the stream in the kitchen", reply)
        self.assertEqual([action for action, _ in self.calls], ["media_stop", "play_media"])

    def test_slow_response_can_still_confirm_a_requested_track_without_retrying(self):
        def start_then_timeout(player, data):
            player.update(state="playing", attributes={**self.track, "media_content_id": data["media_id"]})
            raise TimeoutError

        self.play_response = start_then_timeout
        self.assertEqual(self.play("play islands in the stream in the kitchen")[1], "confirmed")
        self.assertEqual([action for action, _ in self.calls], ["media_stop", "play_media"])

    def test_genre_request_reports_playback_without_claiming_genre_was_verified(self):
        def start_then_timeout(player, data):
            player.update(state="playing", attributes={
                **self.track, "media_content_id": "spotify--account://track/another",
            })
            raise TimeoutError

        self.play_response = start_then_timeout
        self.search_results = {"playlists": [{"name": "Country Music", "uri": "spotify://playlist/country"}]}
        reply, outcome = self.play("play country music in the bedroom")
        self.assertEqual(outcome, "partial")
        self.assertIn("Spotify started playing in the bedroom", reply)
        self.assertIn("couldn't verify the requested selection", reply)
        self.assertEqual([action for action, _ in self.calls], ["media_stop", "play_media"])
        self.assertEqual(self.calls[0][1]["entity_id"], self.bedroom)

    def test_playlist_can_start_after_the_original_verification_window(self):
        self.players[self.bedroom]["state"] = "idle"
        self.search_results = {"playlists": [{"name": "Country Music", "id": "4Jb4PDWREzNnbZcOHPcZPy"}]}
        reads = 0
        original_open = self.open

        def delayed_playback(request, timeout):
            nonlocal reads
            if request.full_url.endswith("/play_media"):
                original_open(request, timeout)
                self.players[self.bedroom]["state"] = "buffering"
                raise TimeoutError
            if request.data is None and request.full_url.endswith(self.bedroom):
                reads += 1
                if reads == 6:
                    self.players[self.bedroom].update(state="playing", attributes=self.track)
            return original_open(request, timeout)

        with patch.object(self, "open", side_effect=delayed_playback):
            reply, outcome = self.play("play country music in the bedroom")
        self.assertEqual(outcome, "partial")
        self.assertIn("Spotify started playing in the bedroom", reply)
        self.assertEqual([action for action, _ in self.calls], ["play_media"])

    def test_timed_out_request_does_not_claim_playback_restarted(self):
        def time_out(player, data):
            raise TimeoutError

        self.play_response = time_out
        self.search_results = {"playlists": [{"name": "Country Music", "uri": "spotify://playlist/country"}]}
        reply, outcome = self.play("play country music in the bedroom")
        self.assertEqual(outcome, "unverified")
        self.assertIn("took too long", reply)
        self.assertEqual([action for action, _ in self.calls], ["media_stop", "play_media"])

    def test_paused_destination_resumes_and_unknown_destination_is_ignored(self):
        self.players[self.bedroom]["state"] = "paused"
        self.assertEqual(self.play("move the music to the bedroom")[1], "confirmed")
        self.assertEqual(self.play("move the music to the bedroom")[1], "confirmed")
        self.assertEqual([action for action, _ in self.calls], ["media_play"])
        self.assertEqual(music.parse("play music in the garage"), ("garage", None, "spotify"))
        self.assertEqual(self.play("play music in the garage")[1], "unresolved")
        with patch.object(server, "ha_device_connection", return_value=None):
            self.assertEqual(music.play(("kitchen", "track", "spotify"), server.ha_device_connection(), None)[1],
                             "not_configured")

    def test_spotify_default_never_falls_back_to_radio(self):
        self.search_results = {"radio": [{"name": "Country Music", "uri": "tunein://radio/station"}]}
        self.assertEqual(self.play("play country music in the kitchen")[1], "unavailable")
        self.assertEqual(self.calls, [])
        self.assertEqual(self.players[self.bedroom]["state"], "playing")
        self.assertEqual(self.searches[0]["media_type"], ["playlist"])

    def test_explicit_radio_searches_stations_and_leaves_other_rooms_alone(self):
        self.search_results = {"radio": [
            {"name": "Heart London", "uri": "radiobrowser://radio/other"},
            {"name": "Heart London", "uri": "tunein://radio/heart"},
        ]}
        self.assertEqual(self.play("play heart london in the kitchen on tunein")[1], "confirmed")
        self.assertEqual(self.calls, [("play_media", {
            "entity_id": self.kitchen, "media_id": "tunein://radio/heart", "media_type": "radio", "enqueue": "play",
        })])
        self.assertEqual(self.searches[0]["media_type"], ["radio"])
        self.assertEqual(self.players[self.bedroom]["state"], "playing")
        self.assertEqual(music.parse("play heart london on tunein in the kitchen"),
                         ("kitchen", "heart london", "tunein"))
        self.assertEqual(music.parse("play radio heart london in the bedroom"),
                         ("bedroom", "heart london", "radio"))

    def test_search_timeout_keeps_previous_stream_playing(self):
        with patch.object(music, "search_media", side_effect=TimeoutError):
            reply, outcome = self.play("play country music in the kitchen")
        self.assertEqual(outcome, "unverified")
        self.assertIn("search took too long", reply)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.players[self.bedroom]["state"], "playing")

    def test_saved_favourite_bypasses_search_and_matches_the_spotify_track_id(self):
        self.players[self.bedroom]["state"] = "idle"

        def start_track(player, data):
            player.update(state="playing", attributes=self.track)

        self.play_response = start_track
        reply, outcome = self.play("play coward of the county by kenny rogers in the bedroom")
        self.assertEqual(outcome, "confirmed", reply)
        self.assertEqual(self.searches, [])
        self.assertEqual(self.calls[0][1]["media_id"], music.FAVOURITE_TRACK)

    def test_configured_country_playlist_bypasses_search(self):
        playlist = "https://open.spotify.com/playlist/0123456789AbCdEfGhIjKl"
        self.players[self.bedroom]["state"] = "idle"
        with patch.dict(music.os.environ, {"DECLAN_SPOTIFY_PRESETS": json.dumps({"Country Music": playlist + "?si=sample"})}):
            self.play("play country music in the bedroom")
        self.assertEqual(self.searches, [])
        self.assertEqual(self.calls[0][1]["media_id"], playlist)
        self.assertEqual(self.calls[0][1]["media_type"], "playlist")

    def test_saved_favourite_does_not_override_a_different_artist(self):
        self.play("play coward of the county by a different artist in the bedroom")
        self.assertIn('artist:"a different artist"', self.searches[0]["q"])

    def test_direct_spotify_search_reuses_token_and_passes_artist_url(self):
        self.search_results = {"artists": [{"name": "Dolly Parton", "id": "32vWCbZh0xZ4o9gkz4PsEU"}]}
        self.play("play dolly parton in the bedroom")
        self.play("play dolly parton in the bedroom")
        self.assertEqual(self.spotify_tokens, 1)
        self.assertEqual(self.calls[1][1]["media_id"], "https://open.spotify.com/artist/32vWCbZh0xZ4o9gkz4PsEU")
        self.assertEqual(self.calls[1][1]["media_type"], "artist")

    def test_spotify_rate_limit_preserves_playback(self):
        self.spotify_throttled = True
        self.assertIn("Spotify search is being rate limited", self.play("play country music in the kitchen")[0])
        self.assertEqual(self.calls, [])
        self.assertEqual(self.players[self.bedroom]["state"], "playing")

    def test_saving_credentials_replaces_the_cached_token_on_next_search(self):
        music.spotify_search(self, "Dolly Parton", "", ("artist",))
        music.save_spotify_credentials("new-client", "new-secret")
        music.spotify_search(self, "Dolly Parton", "", ("artist",))
        self.assertEqual(self.spotify_tokens, 2)
        self.assertEqual(music.spotify_token[0], ("new-client", "new-secret"))

    def test_artist_request_verifies_the_reported_artist_of_the_new_track(self):
        self.search_results = {"artists": [{"name": "Dolly Parton", "id": "32vWCbZh0xZ4o9gkz4PsEU"}]}

        for artist, expected in (("Norah Jones", "partial"), ("Dolly Parton", "confirmed")):
            with self.subTest(artist=artist):
                self.players[self.bedroom].update(state="playing", attributes=self.track)

                def start_track(player, data):
                    player.update(state="playing", attributes={
                        "media_content_id": "spotify--account://track/another",
                        "media_title": "A song", "media_artist": artist,
                    })

                self.play_response = start_track
                reply, outcome = self.play("play dolly parton in the bedroom")
                self.assertEqual(outcome, expected)
                if expected == "confirmed":
                    self.assertIn("Dolly Parton is playing in the bedroom", reply)

    def test_missing_spotify_credentials_do_not_block_saved_links(self):
        self.players[self.bedroom]["state"] = "idle"
        with patch.dict(music.os.environ, {"DECLAN_SPOTIFY_CLIENT_SECRET": ""}):
            self.assertEqual(self.play("play country music in the bedroom")[1], "not_configured")
            self.assertEqual(self.calls, [])
            self.play("play coward of the county in the bedroom")
        self.assertEqual(self.calls[0][1]["media_id"], music.FAVOURITE_TRACK)
        self.assertEqual(self.spotify_tokens, 0)


