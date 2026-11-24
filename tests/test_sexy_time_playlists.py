"""Sexy Time plays only playlists approved in Settings -> Music playlists."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import test_music as music_fixture
from declan.music import music
from result_pairs import pair_of

ADDED = "spotify://playlist/" + "A" * 22
PINNED = "spotify://playlist/" + "B" * 22
FOUND = "spotify://playlist/" + "C" * 22
LIKED = "spotify://playlist/" + "D" * 22
FIXED = "https://open.spotify.com/playlist/0mQbGXAlmsI3T2Vyfa0IVd"


def url(uri):
    return uri.replace("spotify://", "https://open.spotify.com/", 1)


class ApprovedSexyTimePlaylistTests(music_fixture.MusicFixture):
    def setUp(self):
        super().setUp()
        self.enterContext(patch.dict(music.os.environ, {
            "DECLAN_MUSIC_ASSISTANT_SEARCH": "1", "DECLAN_MUSIC_REPLY_FIRST": "0"}))
        self.spotify_requests = 0
        folder = Path(self.enterContext(TemporaryDirectory()))
        self.catalogue = folder / "spotify-playlists.json"
        self.enterContext(patch.dict(music.os.environ, {"DECLAN_SPOTIFY_PLAYLISTS_FILE": str(self.catalogue)}))

    def open(self, request, timeout):
        if "spotify.com" in request.full_url:
            self.spotify_requests += 1
        return super().open(request, timeout)

    def play_from(self, phrase, origin):
        return pair_of(music.play_result)(music.parse(phrase), ("http://ha", {}, self),
                                          lambda _: (list(self.players.values()), None), origin=origin)

    def play_media_calls(self):
        return [data for name, data in self.calls if name == "play_media"]

    def write(self, **sexy_time):
        self.catalogue.write_text(json.dumps({"sexy_time": {"manual": [], "favourites": [], "excluded": [],
                                                            "discovered": [], **sexy_time}}), encoding="utf-8")

    def weigh(self, uri, weight):
        with music.preference_db() as db:
            db.execute("INSERT OR REPLACE INTO preferences VALUES (?, ?)", (uri, weight))

    def sexy_time(self):
        self.calls.clear()
        for row in self.players.values():
            row.update(state="idle", attributes={})
        reply, outcome = self.play_from("play sexy time music in the bedroom", None)
        self.assertEqual(outcome, "confirmed", reply)
        return self.play_media_calls()[0]["media_id"]

    def test_only_added_pinned_or_liked_playlists_play(self):
        self.write(manual=[ADDED], favourites=[PINNED], discovered=[FOUND, LIKED])
        self.weigh(LIKED, 2)
        played = {self.sexy_time() for _ in range(12)}
        self.assertEqual(played, {url(ADDED), url(PINNED), url(LIKED)})
        self.assertEqual(self.spotify_requests, 0)

    def test_disliked_and_excluded_playlists_never_play(self):
        self.write(manual=[ADDED, PINNED], excluded=[PINNED])
        self.weigh(LIKED, 0)
        self.assertEqual({self.sexy_time() for _ in range(5)}, {url(ADDED)})

    def test_recent_playlists_rest_while_there_is_another(self):
        self.write(manual=[ADDED, PINNED])
        first = self.sexy_time()
        with music.preference_db() as db:
            db.execute("INSERT INTO recent_playlists(category, uri) VALUES (?, ?)",
                       ("sexy time music", music.media_key(first)))
        self.assertNotEqual(self.sexy_time(), first)

    def test_with_nothing_approved_the_fixed_playlist_plays(self):
        self.write(discovered=[FOUND])
        self.assertEqual(self.sexy_time(), FIXED)
        self.catalogue.unlink()
        self.assertEqual(self.sexy_time(), FIXED)

    def test_other_routines_and_categories_are_unchanged(self):
        self.assertIsNone(music.approved_playlist("romantic dinner music", catalogue={}))
        self.assertIsNone(music.approved_playlist("braai music", catalogue={"braai": {"manual": [ADDED]}}))
        self.assertEqual(music.approved_playlist("sexy time music", catalogue={"sexy_time": {"manual": [ADDED]}}),
                         (url(ADDED), "playlist", "Sexy Time"))

