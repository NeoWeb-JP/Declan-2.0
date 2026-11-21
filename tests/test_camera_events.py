"""FUT-41: read-only camera event questions from Frigate's Home Assistant entities."""
import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from declan.core.execution_results import Outcome
from declan.ha import camera_events as cams
from declan.turn import house_questions

NOW = datetime(2026, 11, 23, 15, 0).astimezone()  # 3pm wherever the tests run


def ago(**delta):
    return (NOW - timedelta(**delta)).isoformat()


def rows(**overrides):
    base = {
        "binary_sensor.front_door_person_occupancy": ["off", ago(minutes=20), ago(minutes=25)],
        "binary_sensor.front_door_car_occupancy": ["off", ago(days=3), "unknown"],
        "binary_sensor.garden_person_occupancy": ["off", ago(hours=2), ago(hours=2)],
        "binary_sensor.garden_dog_occupancy": ["on", ago(minutes=1), ago(minutes=1)],
        "binary_sensor.garden_cat_occupancy": ["off", ago(days=1), ago(days=1)],
        "binary_sensor.driveway_car_occupancy": ["off", ago(hours=1), ago(minutes=61)],
        "camera.front_door": ["recording", "", ""],
        "camera.garden": ["recording", "", ""],
        "camera.driveway": ["recording", "", ""],
    }
    base.update(overrides)
    return [[entity, *values] for entity, values in base.items()]


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
    def __init__(self, body):
        self.body = body
        self.calls = 0

    def open(self, request, timeout=None):
        self.calls += 1
        return Response(self.body)


def ask(phrase, guest=False, **overrides):
    ha = FakeHA(rows(**overrides))
    return cams.result(cams.match(phrase), ("http://ha", {}, ha), guest=guest, now=NOW), ha


class MatchTests(unittest.TestCase):
    def test_phrases(self):
        cases = {
            "was someone at the front door?": ("was", "person", "at", "front door"),
            "has anyone been at the door today": ("was", "person", "at", "door"),
            "is anyone in the garden?": ("now", "person", "in", "garden"),
            "is a pet in the garden": ("now", "pet", "in", "garden"),
            "is there a car on the drive": ("now", "car", "on", "drive"),
            "when did a car last arrive?": ("when", "car", None, None),
            "when was the last car on the driveway": ("when", "car", "on", "driveway"),
            "when was the last visitor": ("when", "person", None, None),
        }
        for phrase, expected in cases.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(cams.match(phrase), expected)

    def test_not_camera_questions(self):
        for phrase in ("is anyone in", "is anyone at home", "who's home", "turn on the garden lights", None):
            with self.subTest(phrase=phrase):
                self.assertIsNone(cams.match(phrase))
        self.assertEqual(house_questions.match("is anyone home")[0], "presence")
        self.assertEqual(house_questions.match("is anyone in the garden")[0], "cameras")


class AnswerTests(unittest.TestCase):
    def test_was_someone_at_the_door(self):
        result, _ = ask("was someone at the front door?")
        self.assertEqual((result.reply, result.outcome),
                         ("Yes, someone was at the front door about 25 minutes ago.", Outcome.CHAT_ANSWER))
        result, _ = ask("has anyone been at the door")  # "door" finds front_door
        self.assertIn("front door", result.reply)

    def test_not_today(self):
        result, _ = ask("was there a car at the front door")
        self.assertTrue(result.reply.startswith("Not today. A car was last at the front door on "))

    def test_is_anyone_there_now(self):
        result, _ = ask("is anyone in the garden")
        self.assertEqual(result.reply, f"No, nobody in the garden right now. Last seen at {(NOW - timedelta(hours=2)):%H:%M}.")
        result, _ = ask("is anyone in the garden", **{"binary_sensor.garden_person_occupancy": ["on", ago(minutes=1), ""]})
        self.assertEqual(result.reply, "Yes, there's someone in the garden right now.")

    def test_pets_mean_dogs_or_cats(self):
        self.assertEqual(ask("is a pet in the garden")[0].reply, "Yes, there's a dog in the garden right now.")

    def test_when_did_a_car_last_arrive_across_cameras(self):
        result, _ = ask("when did a car last arrive")
        self.assertEqual(result.reply, f"A car was on the driveway at {(NOW - timedelta(minutes=61)):%H:%M}.")

    def test_never_names_anyone(self):
        for phrase in ("was someone at the front door", "is anyone in the garden", "when was the last visitor"):
            reply = ask(phrase)[0].reply
            self.assertNotRegex(reply, r"\b(?:Jaco|Edd)\b")

    def test_offline_is_not_the_same_as_nothing_seen(self):
        result, _ = ask("was someone at the front door", **{"camera.front_door": ["unavailable", "", ""]})
        self.assertEqual((result.reply, result.outcome),
                         ("The front door camera is offline, so I can't tell.", Outcome.UNAVAILABLE))
        result, _ = ask("was someone at the front door", **{
            "binary_sensor.front_door_person_occupancy": ["off", "", "unknown"]})
        self.assertEqual((result.reply, result.outcome),
                         ("Frigate hasn't seen people at the front door lately.", Outcome.CHAT_ANSWER))

    def test_unknown_place_and_object(self):
        self.assertEqual(ask("is anyone in the lounge")[0].reply, "I haven't got a camera on the lounge.")
        self.assertEqual(ask("is a cat on the driveway")[0].outcome, Outcome.UNRESOLVED)

    def test_guest_mode_hides_it_without_asking_home_assistant(self):
        with patch("declan.turn.line_freshness.pick", side_effect=lambda key, lines, **_: lines[0]):
            result, ha = ask("was someone at the front door", guest=True)
        self.assertEqual((result.outcome, ha.calls), (Outcome.REJECTED, 0))
        self.assertIn(result.reply, cams.GUEST_LINES)

    def test_frigate_missing_or_home_assistant_down(self):
        result = cams.result(("now", "person", "in", "garden"), ("http://ha", {}, FakeHA([])), guest=False, now=NOW)
        self.assertEqual(result.outcome, Outcome.NOT_CONFIGURED)

        class Down:
            def open(self, request, timeout=None):
                raise OSError("down")
        result = cams.result(("now", "person", "in", "garden"), ("http://ha", {}, Down()), guest=False, now=NOW)
        self.assertEqual(result.outcome, Outcome.UNAVAILABLE)

    def test_relative_times(self):
        self.assertEqual(cams.when(NOW - timedelta(seconds=30), NOW), "just now")
        self.assertEqual(cams.when(NOW - timedelta(minutes=5), NOW), "about 5 minutes ago")
        self.assertEqual(cams.when(NOW - timedelta(days=10), NOW), f"on {(NOW - timedelta(days=10)).day} "
                                                                  f"{(NOW - timedelta(days=10)):%B}")


if __name__ == "__main__":
    unittest.main()
