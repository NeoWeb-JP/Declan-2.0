"""Verify Spotify market environment defaults against outgoing search requests."""
import os
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import music


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, *_args):
        return b'{"tracks": {"items": []}}'


class _Opener:
    def __init__(self):
        self.requests = []

    def open(self, request, timeout=None):
        self.requests.append(request.full_url)
        return _Response()


class SpotifyMarketEnvironmentDefaultsTests(unittest.TestCase):
    def search(self, settings):
        opener = _Opener()
        credentials = ("test-client", "test-secret")
        with patch.dict(os.environ, settings, clear=True), patch.object(
                music, "spotify_credentials", return_value=(credentials, "environment")), patch.object(
                music.RUNTIME, "spotify_token", (credentials, "test-access-token", float("inf"))):
            try:
                result = music.spotify_search(opener, "example", "", ("track",))
                return result, opener.requests, None
            except ValueError as error:
                return None, opener.requests, str(error)

    def test_unset_defaults_to_gb(self):
        _, urls, error = self.search({})
        self.assertIsNone(error)
        self.assertEqual(parse_qs(urlsplit(urls[0]).query)["market"], ["GB"])

    def test_override_is_trimmed_and_uppercased(self):
        _, urls, error = self.search({"DECLAN_SPOTIFY_MARKET": " za "})
        self.assertIsNone(error)
        self.assertEqual(parse_qs(urlsplit(urls[0]).query)["market"], ["ZA"])

    def test_empty_and_invalid_values_fail_before_search_request(self):
        for market in ("", " ", "GBR", "1A", "G B", "UK?"):
            with self.subTest(market=market):
                _, urls, error = self.search({"DECLAN_SPOTIFY_MARKET": market})
                self.assertEqual(urls, [])
                self.assertIn("two-letter country code", error)


if __name__ == "__main__":
    unittest.main()
