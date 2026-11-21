"""FUT-29: a short morning briefing from configured sources; missing sources skipped silently."""
import json
import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from declan.core.execution_results import Outcome
from declan.ha import briefing, house_info
from declan.turn import house_questions

NOW = datetime(2026, 11, 23, 7, 0, tzinfo=timezone.utc)  # a Monday


class Response:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return json.dumps(self.body).encode()


class FakeHA:
    def __init__(self, *, forecast=None, events=None, bins_events=None, bins_state=None, down=()):
        self.forecast = forecast if forecast is not None else [
            {"condition": "rainy", "temperature": 11.4, "templow": 5, "precipitation_probability": 70}]
        self.events = events if events is not None else [
            {"start": "2026-11-23T10:00:00", "summary": "Dentist"},
            {"start": "2026-11-23", "summary": "Edd's birthday"}]
        self.bins_events = bins_events if bins_events is not None else [
            {"start": "2026-11-24", "summary": "Recycling"}]
        self.bins_state = bins_state
        self.down = down
        self.paths = []

    def open(self, request, timeout=None):
        path = request.full_url.removeprefix("http://ha")
        self.paths.append(path)
        if any(path.startswith(prefix) for prefix in self.down):
            raise OSError("down")
        data = json.loads(request.data) if request.data else {}
        if path.startswith("/api/services/weather/"):
            return Response({"service_response": {data["entity_id"]: {"forecast": self.forecast}}})
        if path.startswith("/api/services/calendar/"):
            return Response({"service_response": {entity: {"events": self.bins_events if entity == "calendar.bins"
                                                           else self.events} for entity in data["entity_id"]}})
        if path == "/api/template" and "states.calendar" in data["template"]:
            return Response(["calendar.family", "calendar.bins"])
        if path == "/api/template":  # the car
            return Response({"charger": [["sensor.psl_1_status", "charging"]], "battery": "64", "guest": "off"})
        if path.startswith("/api/states/"):
            return Response(self.bins_state or {})
        raise AssertionError(path)


class BriefingTestCase(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.enterContext(patch.object(house_info, "PATH", Path(tmp.name) / "house-info.json"))
        self.enterContext(patch.dict(os.environ, {key: "" for key in house_info.ENVIRONMENT.values()}
                                     | {"DECLAN_WEATHER_ENTITY": "weather.home"}))
        house_info.save({"car_name": "the Peugeot", "car_battery": "sensor.car_battery", "bins": "calendar.bins"})

    def brief(self, guest=False, **fake):
        ha = FakeHA(**fake)
        return briefing.compose(("http://ha", {}, ha), guest=guest, now=NOW), ha


class BriefingTests(BriefingTestCase):
    def test_phrases(self):
        for phrase in ("what's my day look like", "What does my day look like?", "morning briefing", "brief me",
                       "give me the briefing", "good morning Declan, what's my day look like"):
            with self.subTest(phrase=phrase):
                self.assertEqual(briefing.match(phrase), ("briefing",))
        for other in ("good morning", "what's the weather", "turn on the lights", None):
            with self.subTest(phrase=other):
                self.assertIsNone(briefing.match(other))
        self.assertEqual(house_questions.match("brief me"), ("briefing", ("briefing",)))

    def test_everything(self):
        text, _ = self.brief()
        self.assertEqual(text, "Today: rain, a high of 11 and a low of 5, 70% chance of rain. "
                               "Bins: Recycling tomorrow, so out they go tonight. "
                               "On the calendar: Edd's birthday and Dentist at 10:00. "
                               "The Peugeot's at 64% and charging.")
        self.assertLessEqual(len(text.split()), briefing.MAX_WORDS)

    def test_all_calendars_except_the_bins_by_default(self):
        _, ha = self.brief()
        self.assertIn("/api/template", ha.paths)
        house_info.save({"calendars": "calendar.family"})
        _, ha = self.brief()
        self.assertEqual(ha.paths.count("/api/template"), 1)  # only the car

    def test_reads_only_configured_sources(self):
        house_info.save({"briefing": "weather"})
        text, ha = self.brief()
        self.assertTrue(text.startswith("Today:"))
        self.assertEqual(len(ha.paths), 1)
        house_info.save({"briefing": ""})
        text, ha = self.brief()
        self.assertEqual((text, ha.paths), ("", []))

    def test_missing_sources_are_skipped_silently(self):
        text, _ = self.brief(down=("/api/services/weather/", "/api/services/calendar/"))
        self.assertEqual(text, "The Peugeot's at 64% and charging.")
        text, _ = self.brief(forecast=[], events=[], bins_events=[])
        self.assertEqual(text, "Nothing on the calendar. The Peugeot's at 64% and charging.")

    def test_guests_get_weather_and_bins_only(self):
        text, ha = self.brief(guest=True)
        self.assertNotIn("Dentist", text)
        self.assertNotIn("Peugeot", text)
        self.assertIn("Bins", text)

    def test_long_calendars_are_trimmed(self):
        events = [{"start": f"2026-11-23T{hour:02d}:00:00", "summary": f"Meeting {hour}"} for hour in range(9, 17)]
        text, _ = self.brief(events=events)
        self.assertIn("Meeting 9 at 09:00, Meeting 10 at 10:00, Meeting 11 at 11:00 and 5 more", text)
        self.assertLessEqual(len(text.split()), briefing.MAX_WORDS)

    def test_bins_from_a_sensor(self):
        house_info.save({"bins": "sensor.recycling"})
        text, _ = self.brief(bins_state={"state": "Tomorrow", "attributes": {"friendly_name": "Recycling"}})
        self.assertIn("Recycling: Tomorrow.", text)
        text, _ = self.brief(bins_state={"state": "3", "attributes": {"friendly_name": "Recycling", "daysTo": 3}})
        self.assertNotIn("Recycling", text)
        text, _ = self.brief(bins_state={"state": "1", "attributes": {"friendly_name": "Recycling", "daysTo": 1}})
        self.assertIn("Recycling: tomorrow.", text)

    def test_result_and_nothing_configured(self):
        result = briefing.result(("briefing",), ("http://ha", {}, FakeHA()), guest=False)
        self.assertEqual(result.outcome, Outcome.CHAT_ANSWER)
        house_info.save({"briefing": ""})
        self.assertEqual(briefing.result(("briefing",), ("http://ha", {}, FakeHA()), guest=False).outcome,
                         Outcome.NOT_CONFIGURED)
        self.assertEqual(briefing.result(("briefing",), None, guest=False).outcome, Outcome.NOT_CONFIGURED)

    def test_good_morning_switch(self):
        self.assertTrue(briefing.for_good_morning(("http://ha", {}, FakeHA()), guest=False))
        house_info.save({"briefing_in_good_morning": False})
        self.assertEqual(briefing.for_good_morning(("http://ha", {}, FakeHA()), guest=False), "")


class GoodMorningTests(BriefingTestCase):
    def test_briefing_follows_a_successful_good_morning(self):
        from declan.core.execution_results import ExecutionResult
        from declan.turn import routine_execution_dispatch as dispatch
        done = ExecutionResult("Good morning.", Outcome.REPORTED_SUCCESS)
        with patch.object(briefing, "for_good_morning", return_value="Today: sunny.") as brief:
            self.assertEqual(dispatch._with_briefing(done, "conn", {"guest_mode": "off"}).reply,
                             "Good morning. Today: sunny.")
            brief.assert_called_with("conn", guest=False)
            dispatch._with_briefing(done, "conn", {"guest_mode": "on"})
            brief.assert_called_with("conn", guest=True)
        with patch.object(briefing, "for_good_morning", return_value=""):
            self.assertIs(dispatch._with_briefing(done, "conn", {}), done)


class SettingsTests(BriefingTestCase):
    def test_validation_and_normalising(self):
        saved = house_info.save({"briefing": "weather, car", "calendars": " calendar.a ,calendar.b"})["settings"]
        self.assertEqual((saved["briefing"], saved["calendars"]), ("weather,car", "calendar.a,calendar.b"))
        for bad in ({"briefing": "weather,news"}, {"calendars": "sensor.x"}, {"bins": "light.x"}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                house_info.save(bad)
        with patch.dict(os.environ, {"DECLAN_BRIEFING": "Weather, Bins"}):
            os.remove(house_info.PATH)
            self.assertEqual(house_info.get("briefing"), "weather,bins")

    def test_household_view(self):
        from tests.test_household_settings import load_view
        view, _ = load_view()
        self.assertTrue(view.valid_house_info(house_info.listing()))
        self.assertTrue(view.valid_house_info_change({"save_house_info": {
            "briefing": "weather,calendar", "calendars": "calendar.family", "bins": "sensor.recycling",
            "briefing_in_good_morning": False}}))
        self.assertFalse(view.valid_house_info_change({"save_house_info": {"briefing": "news"}}))
        self.assertFalse(view.valid_house_info_change({"save_house_info": {"bins": "light.x"}}))


if __name__ == "__main__":
    unittest.main()
