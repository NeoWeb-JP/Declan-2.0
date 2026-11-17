"""Regression coverage for Spotify credential environment fallback and precedence."""
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import music


class SpotifyCredentialEnvironmentDefaultsTests(unittest.TestCase):
    def read_credentials(self, environment, saved=None):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "spotify-settings.json"
            if saved is not None:
                path.write_text(saved, encoding="utf-8")
            with patch.dict(os.environ, environment, clear=True), patch.object(
                    music, "SPOTIFY_SETTINGS", path):
                return music.spotify_credentials()

    def test_missing_settings_and_environment_are_unconfigured(self):
        self.assertEqual(self.read_credentials({}), (("", ""), "unconfigured"))

    def test_complete_environment_credentials_are_trimmed(self):
        result = self.read_credentials({
            "DECLAN_SPOTIFY_CLIENT_ID": "  test-client  ",
            "DECLAN_SPOTIFY_CLIENT_SECRET": "  test-secret  "})
        self.assertEqual(result, (("test-client", "test-secret"), "environment"))

    def test_partial_or_blank_environment_is_unconfigured(self):
        for settings in (
            {"DECLAN_SPOTIFY_CLIENT_ID": "client"},
            {"DECLAN_SPOTIFY_CLIENT_SECRET": "secret"},
            {"DECLAN_SPOTIFY_CLIENT_ID": "  ", "DECLAN_SPOTIFY_CLIENT_SECRET": "secret"},
        ):
            with self.subTest(settings=settings):
                credentials, source = self.read_credentials(settings)
                self.assertEqual(source, "unconfigured")
                self.assertFalse(all(credentials))

    def test_saved_credentials_take_precedence_over_environment(self):
        saved = json.dumps({"client_id": "saved-client", "client_secret": "saved-secret"})
        result = self.read_credentials({
            "DECLAN_SPOTIFY_CLIENT_ID": "env-client",
            "DECLAN_SPOTIFY_CLIENT_SECRET": "env-secret"}, saved)
        self.assertEqual(result, (("saved-client", "saved-secret"), "saved"))

    def test_invalid_saved_settings_do_not_silently_fall_back(self):
        environment = {
            "DECLAN_SPOTIFY_CLIENT_ID": "env-client",
            "DECLAN_SPOTIFY_CLIENT_SECRET": "env-secret"}
        for saved in ("[]", "{}", '{"client_id": "only-client"}', "not json"):
            with self.subTest(saved=saved):
                with self.assertRaises((ValueError, json.JSONDecodeError)):
                    self.read_credentials(environment, saved)


if __name__ == "__main__":
    unittest.main()
