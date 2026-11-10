"""Check Spotify handoffs without changing live playback."""

import io
import json
import unittest
from urllib.error import HTTPError
from unittest.mock import patch

import music
import server


class MusicTests(unittest.TestCase):
    def setUp(self):
        self.players = {entity: {"entity_id": entity, "state": "idle", "attributes": {}}
                        for entity in music.PLAYERS.values()}
        self.bedroom, self.kitchen, self.group = (music.PLAYERS[room] for room in ("bedroom", "kitchen", "everywhere"))
        self.track = {"media_content_id": "spotify--account://track/example",
                      "media_title": "Coward of the County", "media_artist": "Kenny Rogers"}
        self.players[self.bedroom].update(state="playing", attributes=self.track)
        self.calls = []
        self.stop_works = True
        self.throttled = False
        self.enterContext(patch.object(music, "sleep"))

    def open(self, request, timeout):
        path = request.full_url.removeprefix("http://ha")
        if request.data is None:
            return io.BytesIO(json.dumps(self.players[path.rsplit("/", 1)[1]]).encode())
        data = json.loads(request.data)
        self.calls.append((path.rsplit("/", 1)[1], data))
        player = self.players[data["entity_id"]]
        if path.endswith("/media_stop"):
            if self.stop_works:
                player["state"] = "idle"
        elif path.endswith("/transfer_queue"):
            source = self.players[data["source_player"]]
            player.update(state="playing", attributes=source["attributes"])
            source["state"] = "idle"
        elif path.endswith("/media_play"):
            player["state"] = "playing"
        elif self.throttled:
            raise HTTPError(request.full_url, 429, "Too Many Requests", {}, None)
        else:
            player.update(state="playing", attributes={**self.track, "media_title": data["media_id"]})
        return io.BytesIO(b"[]")

    def play(self, phrase):
        return music.play(music.parse(phrase), ("http://ha", {}, self), lambda _: (list(self.players.values()), None))

    def test_same_track_moves_without_searching_then_moves_everywhere(self):
        self.assertEqual(self.play("play coward of the county by kenny rogers in the kitchen")[1], "confirmed")
        self.assertEqual(self.play("play music everywhere on spotify")[1], "confirmed")
        self.assertEqual(self.calls, [
            ("transfer_queue", {"entity_id": self.kitchen, "source_player": self.bedroom, "auto_play": True}),
            ("transfer_queue", {"entity_id": self.group, "source_player": self.kitchen, "auto_play": True}),
        ])

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

    def test_paused_destination_resumes_and_unknown_destination_is_ignored(self):
        self.players[self.bedroom]["state"] = "paused"
        self.assertEqual(self.play("move the music to the bedroom")[1], "confirmed")
        self.assertEqual(self.play("move the music to the bedroom")[1], "confirmed")
        self.assertEqual([action for action, _ in self.calls], ["media_play"])
        self.assertIsNone(music.parse("play music in the garage"))
        with patch.object(server, "ha_device_connection", return_value=None):
            self.assertEqual(music.play(("kitchen", "track"), server.ha_device_connection(), None)[1],
                             "not_configured")
