"""FUT-47: is it a good day to hang the washing?"""
import json
import os
import unittest
from datetime import datetime
from unittest.mock import patch

from declan.core.execution_results import Outcome
from declan.ha import washing
from declan.turn import house_questions

DRY = {"condition": "sunny", "precipitation_probability": 10, "wind_speed": 12, "temperature": 17}


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
    def __init__(self, forecast, unit="km/h", state="sunny", fail=False):
        self.forecast, self.unit, self.state, self.fail = forecast, unit, state, fail

    def open(self, request, timeout=None):
        if self.fail:
            raise OSError("down")
        if "get_forecasts" in request.full_url:
            entity = json.loads(request.data)["entity_id"]
            return Response({"service_response": {entity: {"forecast": self.forecast}}})
        return Response({"state": self.state, "attributes": {"wind_speed_unit": self.unit}})


def ask(phrase, forecast, hour=9, **fake):
    with patch.dict(os.environ, {"DECLAN_WEATHER_ENTITY": "weather.home"}):
        return washing.result(washing.match(phrase), ("http://ha", {}, FakeHA(forecast, **fake)),
                              now=datetime(2026, 11, 22, hour, 0))


class MatchTests(unittest.TestCase):
    def test_phrases(self):
        cases = {"is it a good day to hang the washing?": ("washing", "today"),
                 "can I put the washing out": ("washing", "today"), "should we hang the sheets out": ("washing", "today"),
                 "will the washing dry tomorrow": ("washing", "tomorrow"),
                 "is tomorrow a good day for drying the laundry": ("washing", "tomorrow"),
                 "is it a drying day": ("washing", "today")}
        for phrase, expected in cases.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(washing.match(phrase), expected)
        for other in ("is the washing in", "what's the weather", "turn on the washing machine", None):
            with self.subTest(phrase=other):
                self.assertIsNone(washing.match(other))
        self.assertEqual(house_questions.match("can I hang the washing out")[0], "washing")
        self.assertEqual(house_questions.match("is the washing in")[0], "presence")


class VerdictTests(unittest.TestCase):
    def test_dry_day(self):
        result = ask("is it a good day to hang the washing", [DRY])
        self.assertEqual((result.reply, result.outcome), ("Yes, today looks dry.", Outcome.CHAT_ANSWER))

    def test_rain_says_no(self):
        reply = ask("can I put the washing out", [{**DRY, "condition": "cloudy", "precipitation_probability": 70}]).reply
        self.assertTrue(reply.startswith("No. 70% chance of rain today."))
        reply = ask("can I put the washing out", [{**DRY, "condition": "snowy", "precipitation_probability": 20}]).reply
        self.assertTrue(reply.startswith("No. Snow today."))

    def test_maybe_rain_is_risky(self):
        reply = ask("can I put the washing out", [{**DRY, "precipitation_probability": 40}]).reply
        self.assertTrue(reply.startswith("Risky. 40% chance of rain today."))

    def test_wind_cold_and_late(self):
        reply = ask("can I put the washing out", [{**DRY, "wind_speed": 40, "temperature": 4}], hour=16).reply
        self.assertEqual(reply, "Yes, today looks dry. It's windy, so use extra pegs. It's cold, so it'll take all day. "
                                "There's not much drying time left today.")
        self.assertIn("extra pegs", ask("can I put the washing out", [{**DRY, "wind_speed": 25}], unit="mph").reply)
        self.assertNotIn("extra pegs", ask("can I put the washing out", [{**DRY, "wind_speed": 25}]).reply)

    def test_tomorrow_uses_the_second_day(self):
        result = ask("will the washing dry tomorrow", [{**DRY, "precipitation_probability": 90}, DRY], hour=20)
        self.assertEqual(result.reply, "Yes, tomorrow looks dry.")

    def test_no_forecast_is_never_guessed(self):
        self.assertEqual(ask("is it a drying day", []).outcome, Outcome.UNAVAILABLE)
        self.assertEqual(ask("will the washing dry tomorrow", [DRY]).outcome, Outcome.UNAVAILABLE)
        self.assertEqual(ask("is it a drying day", [{"temperature": 15}]).outcome, Outcome.UNAVAILABLE)
        self.assertEqual(ask("is it a drying day", [DRY], state="unavailable").outcome, Outcome.UNAVAILABLE)
        self.assertEqual(ask("is it a drying day", [DRY], fail=True).outcome, Outcome.UNAVAILABLE)
        self.assertEqual(washing.result(("washing", "today"), None).outcome, Outcome.NOT_CONFIGURED)


if __name__ == "__main__":
    unittest.main()
