"""Country fallback must preserve ambiguity and HA location precedence."""
import os
import unittest
from unittest.mock import Mock, patch

import conditions


class CountryEnvironmentDefaultsTests(unittest.TestCase):
    def test_unset_country_uses_gb_and_lowercase_override_is_accepted(self):
        candidates = [{"country_code": "GB"}, {"country_code": "ZA"}]
        with patch.object(conditions, "ha_connection", return_value=None):
            with patch.dict(os.environ, {}, clear=True):
                self.assertIs(conditions.nearest_place(Mock(), candidates), candidates[0])
            with patch.dict(os.environ, {"DECLAN_DEFAULT_COUNTRY": "za"}):
                self.assertIs(conditions.nearest_place(Mock(), candidates), candidates[1])

    def test_blank_invalid_and_ambiguous_country_do_not_guess(self):
        with patch.object(conditions, "ha_connection", return_value=None):
            for value in ("", " GB ", "invalid", "ZA"):
                with self.subTest(value=value), patch.dict(
                        os.environ, {"DECLAN_DEFAULT_COUNTRY": value}):
                    candidates = [{"country_code": "ZA"}, {"country_code": "ZA"}]
                    self.assertIsNone(conditions.nearest_place(Mock(), candidates))

    def test_home_coordinates_take_precedence_over_country_preference(self):
        candidates = [{"country_code": "GB", "latitude": 51, "longitude": 0},
                      {"country_code": "ZA", "latitude": -33, "longitude": 18}]
        with patch.object(conditions, "ha_connection", return_value=("http://ha", {})), \
             patch.object(conditions, "read_json", return_value={"latitude": -33, "longitude": 18}), \
             patch.dict(os.environ, {"DECLAN_DEFAULT_COUNTRY": "GB"}):
            self.assertIs(conditions.nearest_place(Mock(), candidates), candidates[1])
