"""Regression checks using mocked Home Assistant data and local HTTP only."""

import json
from contextlib import ExitStack
from datetime import date
from threading import Thread
from unittest import TestCase
from unittest.mock import patch
from urllib.request import Request, urlopen

import conditions
import device_status
import server
import timers


class CoreTests(TestCase):
    def test_room_selection_prefers_explicit_room(self):
        with patch.object(server, "ha_device_connection", return_value=("url", {}, None)), patch.object(
            server, "read_ha_areas", return_value={"master bedroom": set()}
        ):
            self.assertEqual(server.select_routine("movie time", "satellite")[1]["movie_room"], "bedroom")
            selection = server.select_routine("movie time in the lounge", "satellite")
            self.assertEqual(selection[1]["movie_room"], "lounge")

    def test_routine_success_requires_confirmed_steps(self):
        result = {
            "schema_version": 1, "request_id": "run", "routine_id": "script.movie",
            "outcome": "success", "resolved_action": "start",
            "steps": [
                {"target": "screen", "status": "confirmed"},
                {"target": "projector power", "status": "unverified"},
            ],
        }
        _, outcome, detail = server.format_routine_result(result, "run", "script.movie", "movie", "start", [])
        self.assertEqual(outcome, "partial")
        self.assertIn("couldn't confirm projector power", detail)
        self.assertEqual(
            server.format_routine_result(result, "wrong", "script.movie", "movie", "start", [])[1], "unverified"
        )

    def test_weather_follow_up_keeps_place(self):
        context = conditions.question_context("what's the weather in oxford tomorrow")
        self.assertEqual(conditions.follow_up("what about saturday", context),
                         ("what's the weather forecast saturday in oxford", None))
        self.assertIsNotNone(conditions.follow_up("what about saturday", None)[1])
        self.assertEqual(conditions.forecast_dates(date(2026, 11, 13), "this weekend"),
                         [date(2026, 11, 14), date(2026, 11, 15)])

    def test_unavailable_device_is_not_confirmed(self):
        inventory = [{"entity_id": "light.fairy_lights", "state": "unavailable",
                      "attributes": {"friendly_name": "Fairy Lights"}}]
        _, outcome, entity = device_status.describe("fairy lights", "on", inventory)
        self.assertEqual((outcome, entity), ("unavailable", "light.fairy_lights"))

    def test_screen_position_and_duplicate_names(self):
        inventory = [{"entity_id": device_status.SCREEN, "state": "open",
                      "attributes": {"current_position": 83}}]
        reply, outcome, entity = device_status.describe("projector screen", "down", inventory)
        self.assertEqual((reply, outcome, entity), ("Projector screen is down.", "confirmed", device_status.SCREEN))
        inventory[0]["attributes"]["current_position"] = 30
        self.assertIn("partway down", device_status.describe(entity, "down", inventory)[0])
        self.assertEqual(device_status.describe("projector", "on", inventory)[1], "unresolved")
        inventory.extend({"entity_id": entity, "state": "on", "attributes": {"friendly_name": "Lamp"}}
                         for entity in ("light.bedroom", "light.lounge"))
        reply, outcome, _ = device_status.describe("lamp", "on", inventory)
        self.assertEqual(outcome, "unresolved")
        self.assertIn("Which room?", reply)
        self.assertNotIn("light.", reply)
        self.assertEqual(device_status.parse("what about the lamp", device_status.SCREEN), ("lamp", None))

    def test_on_off_question_prefers_lamp_but_honours_explicit_switch(self):
        inventory = [
            {"entity_id": "light.master_bedroom_queen_lamp", "state": "on",
             "attributes": {"friendly_name": "Queen Lamp"}},
            {"entity_id": "switch.queen_lamp", "state": "off",
             "attributes": {"friendly_name": "Queen Lamp"}},
        ]
        self.assertEqual(device_status.describe("queen lamp", "on", inventory),
                         ("Queen Lamp is on.", "confirmed", "light.master_bedroom_queen_lamp"))
        self.assertEqual(device_status.describe("switch.queen_lamp", "on", inventory),
                         ("Queen Lamp is off.", "confirmed", "switch.queen_lamp"))

    def test_mixed_light_commands_do_not_become_a_routine(self):
        phrase = "turn on the fairy lights and turn off the office light"
        self.assertIsNone(server.select_routine_turn(phrase, None))
        self.assertEqual(server.parse_light_command(phrase), ("fairy lights and turn off office light", "on"))

    def test_timer_duration_limits(self):
        self.assertEqual(timers.duration_seconds("five minutes and ten seconds"), 310)
        for invalid in ("zero seconds", "25 hours", "five minutes and two minutes"):
            with self.subTest(invalid=invalid):
                self.assertIsNone(timers.duration_seconds(invalid))


class ChainingTests(TestCase):
    def test_partial_routine_does_not_skip_lights_on_browser_or_assist(self):
        order = []

        def run_routine(selection, action_results):
            self.assertEqual(selection, ("morning", {}))
            order.append("routine")
            action_results.append({"target": "Dining lights", "status": "unverified"})
            return "Good morning.", "partial", "I couldn't confirm the dining lights."

        def turn_lights(phrase, *, action_results, last_lights, origin_device):
            self.assertEqual(phrase, "turn on the fairy lights")
            order.append("lights")
            action_results.append({"target": "Fairy lights", "status": "confirmed",
                                   "entity_id": "light.fairy_lights"})
            return "Fairy lights are on.", "confirmed"

        with ExitStack() as stack:
            stack.enter_context(patch.dict(server.os.environ, {"DECLAN_ASSIST_TOKEN": "test-token"}))
            stack.enter_context(patch.object(server, "execute_routine", side_effect=run_routine))
            stack.enter_context(patch.object(server, "handle_light_request", side_effect=turn_lights))
            stack.enter_context(patch.object(server, "SESSIONS", server.OrderedDict()))
            history = stack.enter_context(patch.object(server.history, "record"))
            http = stack.enter_context(server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler))
            worker = Thread(target=http.serve_forever, daemon=True)
            worker.start()
            try:
                origin = f"http://127.0.0.1:{http.server_port}"
                for endpoint in ("chat", "assist"):
                    with self.subTest(endpoint=endpoint):
                        order.clear()
                        request = Request(
                            f"{origin}/api/{endpoint}",
                            data=json.dumps({
                                "message": "Run Good Morning and turn on the fairy lights.",
                                "source": "voice", "device_id": "office-muse",
                            }).encode(),
                            headers={"Content-Type": "application/json", "Origin": origin,
                                     "Authorization": "Bearer test-token"},
                        )
                        with urlopen(request, timeout=5) as response:
                            result = json.load(response)
                        self.assertEqual(order, ["routine", "lights"])
                        self.assertEqual(result["outcome"], "partial")
                        self.assertIn("Fairy lights are on.", result["reply"])
                        self.assertEqual([step["status"] for step in result["action_results"]],
                                         ["unverified", "confirmed"])
                        self.assertEqual(history.call_args.args[4], "partial")
            finally:
                http.shutdown()
                worker.join()
