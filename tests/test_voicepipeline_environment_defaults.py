"""Verify VoicePipeline URL and token environment defaults and overrides."""
import os
import unittest
from unittest.mock import patch

import voicepipeline


class VoicePipelineEnvironmentDefaultsTests(unittest.TestCase):
    def request(self, environment):
        with patch.dict(os.environ, environment, clear=True), patch.object(
                voicepipeline, "build_opener") as build:
            response = build.return_value.open.return_value.__enter__.return_value
            response.read.return_value = b"[]"
            try:
                result = voicepipeline.request("GET", "/api/v1/speakers")
                error = None
            except voicepipeline.PipelineError as exc:
                result, error = None, exc
            return result, error, build

    def test_missing_or_empty_url_fails_before_network(self):
        for settings in ({}, {"DECLAN_VOICEPIPELINE_URL": ""}, {
                "DECLAN_VOICEPIPELINE_URL": "  "}):
            with self.subTest(settings=settings):
                _, error, build = self.request(settings)
                self.assertIsNotNone(error)
                self.assertEqual(error.status, 503)
                build.assert_not_called()

    def test_invalid_urls_fail_before_network(self):
        for value in ("file:///tmp/api", "http://user:pass@host", "https://host/path",
                      "https://host?token=secret", "http://["):
            with self.subTest(value=value):
                _, error, build = self.request({"DECLAN_VOICEPIPELINE_URL": value})
                self.assertIsNotNone(error)
                build.assert_not_called()

    def test_url_is_trimmed_and_trailing_slash_removed(self):
        result, error, build = self.request({
            "DECLAN_VOICEPIPELINE_URL": "  http://127.0.0.1:8000/  "})
        self.assertIsNone(error)
        self.assertEqual(result, [])
        request = build.return_value.open.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:8000/api/v1/speakers")
        self.assertIsNone(request.get_header("Authorization"))

    def test_token_is_optional_and_trimmed_when_supplied(self):
        result, error, build = self.request({
            "DECLAN_VOICEPIPELINE_URL": "http://127.0.0.1:8000",
            "DECLAN_VOICEPIPELINE_TOKEN": "  private-token  "})
        self.assertIsNone(error)
        self.assertEqual(result, [])
        request = build.return_value.open.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer private-token")

    def test_blank_token_omits_authorization(self):
        _, error, build = self.request({
            "DECLAN_VOICEPIPELINE_URL": "http://127.0.0.1:8000",
            "DECLAN_VOICEPIPELINE_TOKEN": "   "})
        self.assertIsNone(error)
        request = build.return_value.open.call_args.args[0]
        self.assertIsNone(request.get_header("Authorization"))


if __name__ == "__main__":
    unittest.main()
