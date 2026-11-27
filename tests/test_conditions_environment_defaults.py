"""Verify weather integration environment defaults and credential guards."""
import os
import unittest
from unittest.mock import patch

from declan.core import conditions


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



class WeatherEntityDefaultsTests(unittest.TestCase):
    def run_read(self, settings, *, outdoors_only=False):
        urls = []

        def fake_read(_opener, url, _headers=None, timeout=3, **_kwargs):
            urls.append(url)
            if "/weather." in url:
                return {"state": "sunny", "attributes": {
                    "temperature": 19, "temperature_unit": "°C"}}
            if "/climate." in url or "/sensor." in url:
                return {"state": "21", "attributes": {
                    "current_temperature": 21, "unit_of_measurement": "°C"}}
            return {}

        with patch.dict(os.environ, settings, clear=True), patch.object(
                conditions, "ha_connection", return_value=("http://ha.local", {})), patch.object(
                conditions, "read_json", side_effect=fake_read):
            result = conditions.home_temperatures_result(
                object(), outdoors_only=outdoors_only)
        return result, urls

    def test_unset_defaults(self):
        result, urls = self.run_read({})
        self.assertEqual(result.outcome.value, "confirmed")
        self.assertEqual(urls, [
            "http://ha.local/api/states/weather.forecast_home",
            "http://ha.local/api/states/climate.home",
        ])

    def test_overrides_and_whitespace(self):
        result, urls = self.run_read({
            "DECLAN_WEATHER_ENTITY": " weather.outdoor ",
            "DECLAN_INDOOR_TEMPERATURE_ENTITY": " sensor.room ",
        })
        self.assertEqual(result.outcome.value, "confirmed")
        self.assertEqual(urls, [
            "http://ha.local/api/states/weather.outdoor",
            "http://ha.local/api/states/sensor.room",
        ])

    def test_empty_and_invalid_values_fail_closed(self):
        for settings in (
            {"DECLAN_WEATHER_ENTITY": "", "DECLAN_INDOOR_TEMPERATURE_ENTITY": ""},
            {"DECLAN_WEATHER_ENTITY": "weather.home?query=1",
             "DECLAN_INDOOR_TEMPERATURE_ENTITY": "script.unsafe"},
        ):
            with self.subTest(settings=settings):
                result, urls = self.run_read(settings)
                self.assertEqual(urls, [])
                self.assertEqual(result.outcome.value, "unavailable")

    def test_outdoor_only_does_not_fetch_indoor(self):
        result, urls = self.run_read({}, outdoors_only=True)
        self.assertEqual(result.outcome.value, "confirmed")
        self.assertEqual(urls, ["http://ha.local/api/states/weather.forecast_home"])



class WeatherForecastEnvironmentDefaultsTests(unittest.TestCase):
    def run_forecast(self, settings):
        calls = []

        def fake_read(_opener, url, _headers=None, timeout=3, **kwargs):
            calls.append((url, kwargs.get("data")))
            if url.endswith("/api/config"):
                return {"time_zone": "Europe/London",
                        "unit_system": {"temperature": "°C"}}
            if "/api/states/" in url:
                return {"state": "sunny",
                        "attributes": {"temperature_unit": "°C"}}
            if "/api/services/weather/get_forecasts" in url:
                return {"service_response": {
                    "weather.forecast_home": {"forecast": []},
                    "weather.outdoor": {"forecast": []}}}
            return {}

        with patch.dict(os.environ, settings, clear=True), patch.object(
                conditions, "ha_connection", return_value=("http://ha.local", {})), patch.object(
                conditions, "read_json", side_effect=fake_read):
            result = conditions.home_forecast(object())
        return result, calls

    def test_unset_entity_uses_default_for_state_and_service(self):
        result, calls = self.run_forecast({})
        self.assertEqual(result[2], "°C")
        self.assertEqual([url for url, _ in calls], [
            "http://ha.local/api/config",
            "http://ha.local/api/states/weather.forecast_home",
            "http://ha.local/api/services/weather/get_forecasts?return_response",
        ])
        self.assertEqual(__import__("json").loads(calls[-1][1]),
                         {"entity_id": "weather.forecast_home", "type": "daily"})

    def test_override_is_stripped_and_used_for_state_and_service(self):
        _, calls = self.run_forecast({"DECLAN_WEATHER_ENTITY": " weather.outdoor "})
        self.assertIn("/api/states/weather.outdoor", calls[1][0])
        self.assertEqual(__import__("json").loads(calls[-1][1]),
                         {"entity_id": "weather.outdoor", "type": "daily"})

    def test_empty_and_invalid_entities_make_no_requests(self):
        for value in ("", "sensor.room", "weather.outdoor?query=1"):
            with self.subTest(value=value):
                result, calls = self.run_forecast({"DECLAN_WEATHER_ENTITY": value})
                self.assertEqual(result, ({}, None, None))
                self.assertEqual(calls, [])

    def test_missing_ha_connection_makes_no_requests(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(
                conditions, "ha_connection", return_value=None), patch.object(
                conditions, "read_json") as read:
            self.assertEqual(conditions.home_forecast(object()), ({}, None, None))
            read.assert_not_called()


class SlowHomeAssistantTests(unittest.TestCase):
    """27 Nov 2026: 1-2 s waits made a busy HA look like no forecast for home."""

    def test_home_forecast_reads_wait_long_enough(self):
        timeouts = []

        def fake_read(_opener, url, _headers=None, timeout=3, **_kwargs):
            timeouts.append(timeout)
            return {}
        with patch.dict(os.environ, {"DECLAN_HA_URL": "http://ha.local", "DECLAN_HA_TOKEN": "t"}, clear=True), \
                patch.object(conditions, "read_json", side_effect=fake_read):
            conditions.home_forecast(None)
        self.assertTrue(timeouts)
        self.assertTrue(all(value >= conditions.HA_TIMEOUT >= 5 for value in timeouts), timeouts)

    def test_failed_lookups_are_logged(self):
        class Slow:
            def open(self, request, timeout=None):
                raise TimeoutError("timed out")
        with self.assertLogs("declan.core.conditions", "WARNING") as logs:
            self.assertEqual(conditions.read_json(Slow(), "http://ha.local/api/config", {}, timeout=5), {})
        self.assertIn("/api/config", logs.output[0])
        self.assertIn("TimeoutError", logs.output[0])


if __name__ == "__main__":
    unittest.main()
