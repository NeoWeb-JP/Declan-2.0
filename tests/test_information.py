"""Check information providers without live credentials or network access."""

import json
from datetime import datetime, timezone
from tempfile import TemporaryDirectory
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest import TestCase
from unittest.mock import patch

import conditions
import history
import timers


class FixedClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 11, 13, 23, 30, tzinfo=timezone.utc).astimezone(tz)


class WeatherTests(TestCase):
    def setUp(self):
        self.enterContext(patch.dict(conditions.os.environ, {
            "DECLAN_HA_URL": "http://ha.invalid", "DECLAN_HA_TOKEN": "test",
            "DECLAN_WEATHER_ENTITY": "weather.forecast_home", "DECLAN_INDOOR_TEMPERATURE_ENTITY": "climate.home",
        }))
        self.enterContext(patch.object(conditions, "datetime", FixedClock))
        self.enterContext(patch.object(conditions, "ZoneInfo", return_value=timezone.utc))
        self.enterContext(patch.object(conditions, "read_json", side_effect=self.provider))
        self.current = {"temperature_2m": 10, "weather_code": 2}

    def provider(self, opener, url, headers=None, timeout=3, *, data=None):
        path = urlsplit(url).path
        if path == "/api/config":
            return {"latitude": 51.7, "longitude": -1.2, "time_zone": "Europe/London",
                    "unit_system": {"temperature": "°C"}}
        if path == "/api/states/weather.forecast_home":
            return {"state": "rainy", "attributes": {"temperature": 8, "temperature_unit": "°C"}}
        if path == "/api/states/climate.home":
            return {"state": "heat", "attributes": {"current_temperature": 19}}
        if path == "/api/services/weather/get_forecasts":
            self.assertEqual(json.loads(data), {"entity_id": "weather.forecast_home", "type": "daily"})
            return {"service_response": {"weather.forecast_home": {"forecast": [
                {"datetime": "2026-11-14T00:00:00Z", "condition": "rainy", "temperature": 12,
                 "templow": 7, "precipitation_probability": 60}
            ]}}}
        params = parse_qs(urlsplit(url).query)
        if path == "/v1/search":
            def city(name, country, code, lat, lon, zone, region):
                return {"name": name, "country": country, "country_code": code, "latitude": lat,
                        "longitude": lon, "timezone": zone, "admin2": region, "feature_code": "PPL"}

            query = params["name"][0]
            if query == "oxford":
                return {"results": [
                    city("Oxford", "United States", "US", 34, -90, "America/Chicago", "Lafayette"),
                    city("Oxford", "United Kingdom", "GB", 55, -2, "Europe/London", "Other County"),
                    city("Oxford", "United Kingdom", "GB", 51.75, -1.26, "Europe/London", "Oxfordshire"),
                ]}
            if query == "sydney" and params.get("countryCode") == ["AU"]:
                return {"results": [city("Sydney", "Australia", "AU", -33.86, 151.21, "Australia/Sydney", "Sydney")]}
            return {"results": []}
        if params.get("daily"):
            return {"daily": {"time": ["2026-11-14"], "weather_code": [95], "temperature_2m_max": [24],
                              "temperature_2m_min": [13], "precipitation_probability_max": [80]}}
        return {"current": self.current}

    def check(self, phrase, outcome, *parts):
        reply, actual, _ = conditions.handle(phrase, None)
        self.assertEqual(actual, outcome, reply)
        for part in parts:
            self.assertIn(part, reply)
        return reply

    def test_current_weather_and_temperature(self):
        self.check("what's the weather like outside", "confirmed", "raining", "8 degrees", "19 degrees")
        reply = self.check("what's the temperature outside", "confirmed", "8 degrees")
        self.assertNotIn("inside", reply)
        self.check("what's the temperature inside", "confirmed", "19 degrees")
        self.assertIsNone(conditions.handle("what's the temp outside", None))

    def test_home_forecast_and_missing_day(self):
        self.check("what's the forecast tomorrow", "confirmed", "Saturday", "raining", "12", "7", "60")
        reply = self.check("what will the temperature be tomorrow", "confirmed", "12", "7")
        self.assertNotIn("raining", reply)
        self.check("will it rain tomorrow", "confirmed", "60")
        self.check("what's the forecast this weekend", "partial", "Sunday", "couldn't verify")
        self.check("what's the forecast on monday", "unavailable", "Monday")

    def test_nearest_place_explicit_country_and_time(self):
        self.check("what's the weather in oxford", "confirmed", "Oxfordshire", "partly cloudy")
        self.check("what's the temperature in oxford", "confirmed", "10 degrees")
        self.check("what's the forecast in oxford tomorrow", "confirmed", "thunderstorms", "Oxfordshire")
        self.check("what time is it in sidney", "confirmed", "Cheshire", "23:30")
        self.check("what's the time in sidney australia", "confirmed", "Sydney, Australia")
        self.check("what's the weather in nowhere", "unresolved", "couldn't find")
        self.current.pop("weather_code")
        self.check("what's the weather in oxford", "partial", "couldn't verify the conditions")


class TimerAndHistoryTests(TestCase):
    def setUp(self):
        temp = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(patch.object(timers, "DATABASE", temp / "timers.sqlite3"))
        self.enterContext(patch.object(history, "DATABASE", temp / "history.sqlite3"))
        self.now = 1000
        self.enterContext(patch.object(timers, "time", side_effect=lambda: self.now))
        self.output = self.enterContext(patch.object(
            timers, "resolve_output", return_value=("assist_satellite.kitchen", "Kitchen")
        ))

    def test_cross_room_timer_lifecycle(self):
        self.assertEqual(timers.handle("set a pasta timer for five minutes in the kitchen", None)[1], "timer_set")
        self.assertEqual(self.output.call_args.kwargs["room"], "kitchen")
        self.assertEqual(timers.handle("set a pasta timer for five minutes in the kitchen", None)[1], "unresolved")
        reply, outcome = timers.handle("how much time is left on my pasta timer", None)
        self.assertEqual(outcome, "timer_status")
        self.assertIn("Kitchen", reply)
        self.assertEqual(timers.handle("stop my pasta timer", None)[1], "unresolved")
        self.assertEqual(timers.handle("cancel my pasta timer", None)[1], "timer_cancelled")
        self.assertEqual(timers.handle("list timers", None)[1], "no_timer")

    def test_timer_alarm_repeats_until_acknowledged(self):
        timers.handle("set a timer for five seconds", None)
        self.now += 5
        with patch.object(timers, "ha_json", return_value=[]) as announce:
            timers.ring_due(None)
            timers.ring_due(None)
            self.assertEqual(announce.call_count, 1)
            self.now += timers.ALARM_INTERVAL
            timers.ring_due(None)
            self.assertEqual(announce.call_count, 2)
            self.assertEqual(announce.call_args.kwargs["data"]["entity_id"], "assist_satellite.kitchen")
            self.assertTrue(announce.call_args.kwargs["data"]["preannounce"])
            self.assertIn("timer is up", announce.call_args.kwargs["data"]["message"])
            self.assertEqual(timers.handle("stop my timer", None)[1], "timer_stopped")
            self.now += timers.ALARM_INTERVAL
            timers.ring_due(None)
            self.assertEqual(announce.call_count, 2)

    def test_timer_adjustment_uses_remaining_time_and_reschedules_alarm(self):
        self.output.return_value = ("assist_satellite.bedroom", "Master Bedroom")
        timers.handle("set a five minute timer", None)
        self.now += 60
        reply, outcome = timers.handle("decrease the time on the master bedroom timer by two minutes", None)
        self.assertEqual(outcome, "timer_adjusted")
        self.assertIn("2 minutes left", reply)
        reply, outcome = timers.handle("increase my five minute timer in the master bedroom by one minute", None)
        self.assertEqual(outcome, "timer_adjusted")
        self.assertIn("3 minutes left", reply)
        with patch.object(timers, "ha_json", return_value=[]) as announce:
            self.now += 120
            timers.ring_due(None)
            announce.assert_not_called()
            self.assertEqual(timers.handle("decrease my timer by two minutes", None)[1], "timer_adjusted")
            timers.ring_due(None)
            announce.assert_called_once()
            self.assertEqual(timers.handle("increase my timer by one minute", None)[1], "unresolved")

    def test_history_shows_confident_assist_matches_and_keeps_uncertain_matches_unknown(self):
        for source, confidence in (("assist", 0.9), ("assist", 0.4), ("browser_voice", 0.99)):
            history.record("session", source, "question", "answer", speaker={
                "name": "Ed", "confidence": confidence, "interaction_id": "match-123",
            })
        browser, uncertain, confident = history.recent()
        self.assertIsNone(browser["speaker_match"])
        self.assertEqual(uncertain["speaker_match"], {
            "name": "Unknown", "candidate": "Edd", "confidence": 0.4, "interaction_id": "match-123",
        })
        self.assertEqual(confident["speaker_match"], {
            "name": "Edd", "confidence": 0.9, "interaction_id": "match-123",
        })

    def test_history_records_routine_evidence_and_paginates(self):
        history.record("session", "assist", "good morning", "Morning", "partial", "Dining lights unverified",
                       [{"target": "Dining lights", "status": "unverified"}])
        history.record("session", "browser_voice", "hello", "Hello")
        latest, prior = history.recent()
        self.assertEqual(history.recent(latest["id"])[0]["id"], prior["id"])
        self.assertEqual(prior["action_results"][0]["status"], "unverified")
        self.assertTrue(history.has_recent_assist())
        history.prune()
