"""Verify weather integration environment defaults and credential guards."""
import os
import unittest
from unittest.mock import patch

import conditions


class ConditionsEnvironmentDefaultsTests(unittest.TestCase):
    def test_unset_or_empty_connection_is_disabled(self):
        for settings in ({}, {"DECLAN_HA_URL": "", "DECLAN_HA_TOKEN": ""},
                         {"DECLAN_HA_URL": "http://ha.local"},
                         {"DECLAN_HA_TOKEN": "secret"}):
            with self.subTest(settings=settings), patch.dict(os.environ, settings, clear=True):
                self.assertIsNone(conditions.ha_connection())

    def test_connection_normalizes_url_and_token(self):
        with patch.dict(os.environ, {"DECLAN_HA_URL": " https://ha.local:8123/ ",
                                     "DECLAN_HA_TOKEN": " secret "}, clear=True):
            self.assertEqual(conditions.ha_connection(),
                             ("https://ha.local:8123", {"Authorization": "Bearer secret"}))

    def test_rejects_invalid_or_credential_bearing_urls(self):
        for url in ("file:///etc/passwd", "not-a-url", "https://user:pass@ha.local",
                    "https://ha.local/?token=secret", "https://ha.local/#fragment"):
            with self.subTest(url=url), patch.dict(os.environ, {
                    "DECLAN_HA_URL": url, "DECLAN_HA_TOKEN": "secret"}, clear=True):
                self.assertIsNone(conditions.ha_connection())


    def test_default_country_prefers_unique_gb_candidate_without_ha(self):
        candidates = [{"name": "Example UK", "country_code": "GB"},
                      {"name": "Example ZA", "country_code": "ZA"}]
        with patch.dict(os.environ, {}, clear=True):
            self.assertIs(conditions.nearest_place(None, candidates), candidates[0])

    def test_country_override_is_case_insensitive(self):
        candidates = [{"name": "Example UK", "country_code": "GB"},
                      {"name": "Example ZA", "country_code": "ZA"}]
        with patch.dict(os.environ, {"DECLAN_DEFAULT_COUNTRY": "za"}, clear=True):
            self.assertIs(conditions.nearest_place(None, candidates), candidates[1])

    def test_country_selection_fails_closed_for_ambiguous_or_empty_preference(self):
        candidates = [{"name": "One", "country_code": "GB"},
                      {"name": "Two", "country_code": "GB"}]
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(conditions.nearest_place(None, candidates))
        with patch.dict(os.environ, {"DECLAN_DEFAULT_COUNTRY": ""}, clear=True):
            self.assertIsNone(conditions.nearest_place(None, candidates))


if __name__ == "__main__":
    unittest.main()
