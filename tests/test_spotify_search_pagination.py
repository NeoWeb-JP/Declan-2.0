"""Spotify playlist discovery uses 2026-compliant paginated searches."""
import io
import json
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import music


class FakeSpotify:
    def __init__(self, total=25):
        self.total = total
        self.requests = []

    def open(self, request, timeout=None):
        url = request.full_url
        if "accounts.spotify.com" in url:
            return io.BytesIO(json.dumps({"access_token": "token", "expires_in": 3600}).encode())
        params = parse_qs(urlsplit(url).query)
        self.requests.append(params)
        offset = int(params.get("offset", ["0"])[0])
        limit = int(params["limit"][0])
        items = [{"id": f"{i:022d}", "name": f"Playlist {i}"}
                 for i in range(offset, min(offset + limit, self.total))]
        return io.BytesIO(json.dumps({"playlists": {"items": items}}).encode())


class SpotifyPaginationTests(unittest.TestCase):
    def setUp(self):
        music.spotify_token = None
        self.addCleanup(setattr, music, "spotify_token", None)

    def test_collects_25_playlists_in_ten_ten_five_pages(self):
        fake = FakeSpotify()
        with patch.object(music, "spotify_credentials", return_value=(("client", "secret"), None)):
            result = music.spotify_search(fake, "country music", "", ("playlist",))
        self.assertEqual(len(result), 25)
        self.assertEqual([int(x["limit"][0]) for x in fake.requests], [10, 10, 5])
        self.assertEqual([int(x["offset"][0]) for x in fake.requests], [0, 10, 20])
        self.assertTrue(all(x["type"] == ["playlist"] for x in fake.requests))

    def test_short_result_stops_pagination(self):
        fake = FakeSpotify(total=4)
        with patch.object(music, "spotify_credentials", return_value=(("client", "secret"), None)):
            result = music.spotify_search(fake, "rock", "", ("playlist",))
        self.assertEqual(len(result), 4)
        self.assertEqual(len(fake.requests), 1)


if __name__ == "__main__":
    unittest.main()
