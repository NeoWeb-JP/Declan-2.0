"""FUT-31: car questions from the Pod Point and the car's battery sensor; charging changes ask first."""
import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from declan.core.execution_results import Outcome
from declan.ha import car, house_info
from declan.turn import house_questions, sensitive_confirmations

POD = "psl_157946"


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
    def __init__(self, status="charging", cable="on", allowed="off", battery="64", charger=True, fail_call=False):
        self.rows = ([[f"sensor.{POD}_status", status], [f"binary_sensor.{POD}_cable_status", cable],
                      [f"switch.{POD}_charging_allowed", allowed], [f"sensor.{POD}_current_energy", "4.2"],
                      [f"sensor.{POD}_cloud_connection_status", "connected"]] if charger else [])
        self.battery = battery
        self.fail_call = fail_call
        self.services = []
        self.templates = []

    def open(self, request, timeout=None):
        data = json.loads(request.data)
        if request.full_url.endswith("/api/template"):
            self.templates.append(data["template"])
            return Response({"charger": self.rows, "battery": self.battery if '"sensor.' in data["template"] else "",
                             "guest": "off"})
        if self.fail_call:
            raise OSError("down")
        self.services.append((request.full_url.split("/api/services/")[1], data["entity_id"]))
        return Response([])


class CarTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = patch.object(house_info, "PATH", Path(self.tmp.name) / "house-info.json")
        patcher.start()
        self.addCleanup(patcher.stop)
        environment = patch.dict(os.environ, {"DECLAN_CAR_NAME": "", "DECLAN_CAR_BATTERY_ENTITY": ""})
        environment.start()
        self.addCleanup(environment.stop)
        house_info.save({"car_name": "the Peugeot", "car_battery": "sensor.vr3_battery"})

    def ask(self, phrase, guest=False, **state):
        ha = FakeHA(**state)
        return car.result(car.match(phrase), ("http://ha", {}, ha), guest=guest), ha


class MatchTests(CarTestCase):
    def test_phrases(self):
        cases = {
            "is the car charged?": ("ask", "battery"), "how much charge has the car got": ("ask", "battery"),
            "what's the car's battery": ("ask", "battery"), "is the Peugeot full": ("ask", "battery"),
            "is the car plugged in": ("ask", "plugged"), "is the car charging": ("ask", "charging"),
            "start charging the car": ("start",), "charge the car": ("start",), "start charging": ("start",),
            "stop charging the car": ("stop",), "turn off the car charger": ("stop",),
        }
        for phrase, expected in cases.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(car.match(phrase), expected)

    def test_not_the_car(self):
        for phrase in ("turn off the charger", "charge my phone", "play some music", "is the car outside", None):
            with self.subTest(phrase=phrase):
                self.assertIsNone(car.match(phrase))

    def test_charging_changes_need_a_spoken_yes(self):
        group = sensitive_confirmations.sensitive_group("start charging the car", None, {}, {}, set())
        self.assertEqual(group, "custom:car_charging")
        self.assertEqual(sensitive_confirmations.sensitive_group("stop charging", None, {}, {}, set()),
                         "custom:car_charging")
        self.assertIsNone(sensitive_confirmations.sensitive_group("is the car charged", None, {}, {}, set()))
        gate = sensitive_confirmations.ConfirmationGate(clock=lambda: 0)
        self.assertEqual(gate.evaluate(session="s", origin="sat", phrase="start charging the car",
                                       group="custom:car_charging", speaker=None)[0], "prompt")
        self.assertEqual(gate.evaluate(session="s", origin="sat", phrase="yes", group=None, speaker=None),
                         ("confirmed", "start charging the car"))


class AnswerTests(CarTestCase):
    def test_battery_and_charging(self):
        result, ha = self.ask("is the car charged")
        self.assertEqual((result.reply, result.outcome), ("The Peugeot's at 64% and charging.", Outcome.CHAT_ANSWER))
        self.assertIn('"sensor.vr3_battery"', ha.templates[0])
        result, _ = self.ask("is the car charged", status="connected-waiting-for-schedule")
        self.assertEqual(result.reply, "The Peugeot's at 64% and plugged in and waiting for its schedule.")
        result, _ = self.ask("is the car charged", status="available", cable="off", battery="15")
        self.assertEqual(result.reply, "The Peugeot's at 15% and not plugged in. "
                                       "Plug it in before it leaves you on the side of the road.")
        result, _ = self.ask("is the car full", status="suspended-ev", battery="100")
        self.assertEqual(result.reply, "The Peugeot's at 100% and plugged in, but the car has stopped taking charge. "
                                       "Full, more or less.")

    def test_plugged_and_charging(self):
        self.assertEqual(self.ask("is the car plugged in")[0].reply, "Yes, the Peugeot's plugged in and charging.")
        self.assertEqual(self.ask("is the car plugged in", status="connected-waiting-for-schedule")[0].reply,
                         "Yes, the Peugeot's plugged in and waiting for its schedule.")
        self.assertTrue(self.ask("is the car plugged in", status="available", cable="off")[0].reply.startswith(
            "No, the Peugeot isn't plugged in."))
        self.assertEqual(self.ask("is the car charging")[0].reply, "Yes, the Peugeot's charging.")
        self.assertEqual(self.ask("is the car charging", status="available", cable="off")[0].reply,
                         "No, the Peugeot's not plugged in.")

    def test_unreporting_sensors_are_said_plainly(self):
        result, _ = self.ask("is the car charged", battery="unavailable")
        self.assertEqual((result.reply, result.outcome),
                         ("I can't see the Peugeot's battery right now. It's charging.", Outcome.UNAVAILABLE))
        result, _ = self.ask("is the car plugged in", status="unavailable", cable="unavailable")
        self.assertEqual(result.outcome, Outcome.UNAVAILABLE)

    def test_no_battery_sensor_answers_from_the_charger(self):
        house_info.save({"car_battery": ""})
        result, ha = self.ask("is the car charged")
        self.assertIn("charging", result.reply)
        self.assertIn("Settings", result.reply)
        self.assertIn('{% set battery = "" %}', ha.templates[0])

    def test_nothing_configured(self):
        house_info.save({"car_battery": ""})
        result, _ = self.ask("is the car charged", charger=False)
        self.assertEqual(result.outcome, Outcome.NOT_CONFIGURED)

    def test_summary_for_the_briefing(self):
        self.assertEqual(car.summary(("http://ha", {}, FakeHA())), "The Peugeot's at 64% and charging.")
        house_info.save({"car_battery": ""})
        self.assertIsNone(car.summary(("http://ha", {}, FakeHA(charger=False))))


class SunriseTests(CarTestCase):
    def fake(self, guest="off", **state):
        ha = FakeHA(**state)

        def call(api, data=None):
            body = ha.open(type("R", (), {"full_url": "http://ha" + api, "data": json.dumps(data)})()).body
            if api == "/api/template":
                body = {**body, "guest": guest}
            return body
        return call

    def test_sunrise_mentions_the_car_unless_guests_or_switched_off(self):
        from declan.timers import sunrise
        self.assertEqual(sunrise._car_line(self.fake()), "The Peugeot's at 64% and charging.")
        self.assertIsNone(sunrise._car_line(self.fake(guest="on")))
        house_info.save({"car_in_sunrise": False})
        self.assertIsNone(sunrise._car_line(self.fake()))

    def test_sunrise_survives_home_assistant_failing(self):
        from declan.timers import sunrise

        def broken(api, data=None):
            raise OSError("down")
        self.assertIsNone(sunrise._car_line(broken))


class ControlTests(CarTestCase):
    def test_start_turns_on_charging_allowed(self):
        result, ha = self.ask("start charging the car", status="connected-waiting-for-schedule")
        self.assertEqual(result.outcome, Outcome.REQUESTED)
        self.assertIn("overrides its schedule", result.reply)
        self.assertEqual(ha.services, [("switch/turn_on", f"switch.{POD}_charging_allowed")])

    def test_start_needs_the_car_plugged_in_and_not_already_charging(self):
        result, ha = self.ask("start charging", status="available", cable="off")
        self.assertEqual((result.outcome, ha.services), (Outcome.UNRESOLVED, []))
        result, ha = self.ask("start charging", status="charging")
        self.assertEqual((result.reply, ha.services), ("The Peugeot's already charging.", []))

    def test_stop_hands_back_to_the_schedule(self):
        result, ha = self.ask("stop charging the car", allowed="on")
        self.assertEqual(result.reply, "Charging stopped. The Pod Point schedule is back in charge.")
        self.assertEqual(ha.services, [("switch/turn_off", f"switch.{POD}_charging_allowed")])
        result, ha = self.ask("stop charging", allowed="off", status="connected-waiting-for-schedule")
        self.assertEqual(ha.services, [])

    def test_guests_and_failures(self):
        result, ha = self.ask("start charging the car", guest=True)
        self.assertEqual((result.outcome, ha.services, ha.templates), (Outcome.REJECTED, [], []))
        self.assertEqual(self.ask("is the car charged", guest=True)[0].outcome, Outcome.CHAT_ANSWER)
        result, _ = self.ask("start charging", status="connected-waiting-for-schedule", fail_call=True)
        self.assertEqual(result.outcome, Outcome.FAILED)
        result, _ = self.ask("start charging", charger=False)
        self.assertEqual(result.outcome, Outcome.NOT_CONFIGURED)
        self.assertEqual(self.ask("start charging", allowed="unavailable")[0].outcome, Outcome.UNAVAILABLE)


class SettingsTests(CarTestCase):
    def test_listing_validation_and_environment(self):
        self.assertEqual(house_info.listing()["sources"], {"car_name": "saved", "car_battery": "saved",
                                                           "car_in_sunrise": "default"})
        with self.assertRaises(ValueError):
            house_info.save({"car_battery": "light.kitchen"})
        with self.assertRaises(ValueError):
            house_info.save({"wifi": "x"})
        os.remove(house_info.PATH)
        with patch.dict(os.environ, {"DECLAN_CAR_BATTERY_ENTITY": "sensor.from_env", "DECLAN_CAR_NAME": "",
                                     "DECLAN_CAR_IN_SUNRISE": "off"}):
            self.assertEqual(house_info.listing()["settings"], {"car_name": "the car", "car_battery": "sensor.from_env",
                                                                "car_in_sunrise": False})

    def test_router(self):
        self.assertEqual(house_questions.match("is the car plugged in"), ("car", ("ask", "plugged")))

    def test_household_view_validation(self):
        from tests.test_household_settings import load_view
        view, _ = load_view()
        self.assertTrue(view.valid_house_info_change({"save_house_info": {"car_name": "the Peugeot",
                                                                         "car_battery": "sensor.x_battery"}}))
        self.assertTrue(view.valid_house_info_change({"save_house_info": {"car_battery": ""}}))
        self.assertFalse(view.valid_house_info_change({"save_house_info": {"car_battery": "light.x"}}))
        self.assertFalse(view.valid_house_info_change({"save_house_info": {}}))
        self.assertTrue(view.valid_house_info_change({"save_house_info": {"car_in_sunrise": False}}))
        self.assertFalse(view.valid_house_info_change({"save_house_info": {"car_in_sunrise": "no"}}))
        self.assertTrue(view.valid_house_info(None))
        self.assertTrue(view.valid_house_info(house_info.listing()))
        self.assertFalse(view.valid_house_info({"settings": {"car_name": "x"}, "sources": {}}))


if __name__ == "__main__":
    unittest.main()
