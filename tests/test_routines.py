"""Verify the request contract and reported routine outcomes."""

import io
import json
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError

import server
from personality import LINES

from test_home_assistant import HA_ENV


class RoutineTests(TestCase):
    def setUp(self):
        self.enterContext(patch.dict(server.os.environ, HA_ENV | {
            "DECLAN_MOVIE_SCRIPT": "script.movie", "DECLAN_MOVIE_REMOTE": "remote.projector",
        }))
        self.enterContext(patch.object(server, "routine_last_attempts", {}))
        self.delay = self.enterContext(patch.object(server, "sleep"))
        self.opener = self.enterContext(patch.object(server, "build_opener")).return_value
        self.calls = []

    def respond(self, payload):
        def open_request(request, timeout):
            self.calls.append(request)
            if request.full_url.endswith("return_response"):
                parameters = json.loads(request.data)
                result = payload(parameters)
                return io.BytesIO(json.dumps({"service_response": result}).encode())
            return io.BytesIO(b'{"state":"on"}')
        self.opener.open.side_effect = open_request

    @staticmethod
    def confirmed(parameters, **extra):
        return {"schema_version": 1, **parameters, "outcome": "success", "guest_mode": "off",
                "steps": [{"target": "lights", "status": "confirmed"}], **extra}

    def test_morning_dispatches_once_and_rejects_duplicate(self):
        self.respond(self.confirmed)
        steps = []
        self.assertEqual(server.run_routine("morning", action_results=steps)[1], "reported_success")
        self.assertIn("/script/declan_good_morning_shared_local_routine?", self.calls[0].full_url)
        self.assertEqual(steps[0]["status"], "confirmed")
        self.assertEqual(server.run_routine("morning")[1], "duplicate")
        self.assertEqual(len(self.calls), 1)

    def test_night_private_facts_depend_on_guest_mode(self):
        for guest in ("on", "off"):
            with self.subTest(guest=guest):
                server.routine_last_attempts.clear()
                self.respond(lambda data: self.confirmed(data, guest_mode=guest, bedtime={
                    "battery_percent": 30, "indoor_temperature": 14,
                }))
                reply, outcome, detail = server.run_routine("night")
                self.assertEqual(outcome, "reported_success")
                self.assertIn("all lights are off", detail)
                self.assertEqual("Peugeot" in reply, guest == "off")
                self.assertEqual("14 degrees" in reply, guest == "off")

    def test_partial_movie_start_and_end_keep_sass_and_verification_details(self):
        for direction in ("start", "end"):
            with self.subTest(direction=direction):
                self.respond(lambda data: self.confirmed(data, resolved_action=direction, outcome="partial", steps=[
                    {"target": "Screen", "status": "confirmed"},
                    {"target": "Projector media player", "status": "unverified"},
                ]))
                reply, outcome, detail = server.run_routine("movie", movie_action=direction)
                self.assertEqual(outcome, "partial")
                self.assertIn("I couldn't confirm Projector media player.", detail)
                intro = "Starting Movie Time. " if direction == "start" else "Ending Movie Time. "
                self.assertTrue(reply.startswith(intro), reply)
                self.assertNotIn("Projector media player", reply)

    def test_movie_app_launch_requires_verified_routine(self):
        selection = server.select_routine("open netflix in the lounge", "bedroom-satellite")
        self.assertEqual(selection, ("movie", {
            "movie_action": "start", "movie_room": "lounge", "requested_app": "netflix",
        }))
        self.respond(lambda data: self.confirmed(data, outcome="partial", resolved_action="start"))
        steps = []
        reply, outcome, _ = server.execute_routine(selection, steps)
        self.assertEqual(outcome, "partial")
        self.assertEqual(steps[-1]["status"], "skipped")
        self.assertEqual(len(self.calls), 1)
        self.delay.assert_not_called()
        server.routine_last_attempts.clear()
        events = []

        def finish(data):
            events.append("script finished")
            return self.confirmed(data, resolved_action="start")

        self.respond(finish)
        def wait(seconds):
            events.append(("delay", seconds))
            if seconds == 2:
                self.assertEqual(json.loads(self.calls[-1].data)["command"], "KEY_HOME")

        self.delay.side_effect = wait
        reply, outcome, _ = server.execute_routine(selection, steps)
        self.assertEqual(outcome, "reported_success")
        self.assertEqual(events, ["script finished", ("delay", 7), ("delay", 2)])
        self.assertIn(reply.removeprefix("Starting Movie Time. "), LINES["movie_start"][0])
        self.assertEqual(steps[-1]["status"], "sent")
        self.assertEqual(json.loads(self.calls[-4].data)["requested_action"], "start")
        self.assertEqual(json.loads(self.calls[-1].data)["command"], "app:netflix")

    def test_movie_app_discovers_home_assistant_script_and_projector_remote(self):
        script = "script.declan_movie_time_shared_local_routine"
        remote = "remote.living_room_living_room_projector_remote"
        inventory = [
            {"entity_id": script},
            {"entity_id": remote},
            {"entity_id": "remote.bedroom_projector_remote"},
            {"entity_id": "script.movie_time"},
        ]
        self.respond(lambda data: self.confirmed(data, resolved_action="start"))
        with patch.dict(server.os.environ, {"DECLAN_MOVIE_SCRIPT": "", "DECLAN_MOVIE_REMOTE": ""}), patch.object(
            server, "read_ha_inventory", return_value=(inventory, None)
        ), patch.object(server, "read_ha_areas", return_value={}):
            steps = []
            _, outcome, _ = server.run_routine(
                "movie", movie_action="start", movie_app=server.MOVIE_APPS["netflix"], action_results=steps,
            )
        self.assertEqual(outcome, "reported_success")
        self.assertIn(f"/api/services/script/{script.split('.')[1]}?", self.calls[0].full_url)
        self.assertEqual(json.loads(self.calls[-1].data), {"entity_id": remote, "command": "app:netflix"})
        self.assertEqual(steps[-1]["entity_id"], remote)
        self.assertIn("Command: app:netflix.", steps[-1]["detail"])

    def test_legacy_movie_launches_after_script_finishes_even_if_projector_state_is_unavailable(self):
        entities = [
            {"entity_id": "script.movie", "state": "on"},
            {"entity_id": "cover.living_room_projector_screen", "state": "unknown"},
            {"entity_id": "switch.projector_power_socket", "state": "on"},
            {"entity_id": "media_player.toptro_vg03f3_037f0808_television", "state": "unavailable"},
        ]
        self.respond(lambda _: {})
        app = server.MOVIE_APPS["netflix"]
        with patch.object(server, "read_ha_inventory", return_value=(entities, None)):
            steps = []
            reply, outcome, _ = server.run_routine("movie", movie_action="start", movie_app=app, action_results=steps)
            self.assertEqual(outcome, "unverified")
            self.assertEqual(steps[-1]["status"], "skipped")
            self.assertIn("script is off", reply)
            self.assertEqual(len(self.calls), 1)
            server.routine_last_attempts.clear()
            entities[0]["state"] = "off"
            self.respond(lambda _: {"schema_version": 1, "request_id": "", "routine_id": "",
                                    "outcome": "success"})
            self.delay.reset_mock()
            reply, outcome, detail = server.run_routine("movie", movie_action="start", movie_app=app)
        self.assertEqual(outcome, "partial")
        self.assertEqual([entry.args for entry in self.delay.call_args_list], [(7,), (2,)])
        self.assertIn("Movie Time has finished and the lounge projector socket is on", detail)
        self.assertIn(reply.removeprefix("Starting Movie Time. "), LINES["movie_start"][1])
        self.assertEqual(json.loads(self.calls[-1].data)["command"], "app:netflix")

    def test_movie_accepts_a_matching_result_wrapped_by_script_entity(self):
        self.respond(lambda data: {"script.movie": self.confirmed(data, resolved_action="start")})
        steps = []
        _, outcome, _ = server.run_routine(
            "movie", movie_action="start", movie_app=server.MOVIE_APPS["netflix"], action_results=steps,
        )
        self.assertEqual(outcome, "reported_success")
        self.assertEqual([entry.args for entry in self.delay.call_args_list], [(7,), (2,)])
        self.assertEqual(steps[-1]["status"], "sent")

    def test_movie_response_from_another_run_cannot_launch_an_app(self):
        self.respond(lambda data: self.confirmed({**data, "request_id": "wrong"}, resolved_action="start"))
        with patch.object(server, "verify_legacy_lounge_start", return_value=True) as fallback:
            _, outcome, _ = server.run_routine("movie", movie_action="start", movie_app=server.MOVIE_APPS["netflix"])
        self.assertEqual(outcome, "unverified")
        self.assertEqual(len(self.calls), 1)
        fallback.assert_not_called()

    def test_movie_discovery_refuses_to_guess_or_use_lounge_script_in_bedroom(self):
        script = "script.declan_movie_time_shared_local_routine"
        inventory = [{"entity_id": script}, {"entity_id": "remote.projector_one"},
                     {"entity_id": "remote.projector_two"}]
        areas = {"living room": {"remote.projector_one", "remote.projector_two"}}
        with patch.object(server, "read_ha_inventory", return_value=(inventory, None)), patch.object(
            server, "read_ha_areas", return_value=areas
        ):
            _, _, lounge_error = server.discover_movie_entities(None, "lounge", script="", remote="", needs_remote=True)
            _, _, bedroom_error = server.discover_movie_entities(None, "bedroom", script="", remote="", needs_remote=False)
        self.assertIn("more than one projector remote", lounge_error)
        self.assertIn("couldn't find a Movie Time script for the bedroom", bedroom_error)

    def test_open_shortcut_requires_known_app_and_room(self):
        self.assertIsNone(server.parse_movie_request("open the blinds in the lounge"))
        self.assertIsNone(server.parse_movie_request("open netflix in the kitchen"))
        self.assertIsNone(server.parse_movie_request("open netflix"))
        self.assertEqual(server.parse_movie_request("open prime video in the bedroom"),
                         ("start", "bedroom", "prime video"))

    def test_launch_is_an_alias_for_open(self):
        for phrase in ("launch netflix in the lounge", "start movie time and launch netflix in the lounge"):
            with self.subTest(phrase=phrase):
                self.assertEqual(server.parse_movie_request(phrase), ("start", "lounge", "netflix"))
        self.assertIsNone(server.parse_movie_request("launch an unsupported app in the lounge"))

    def test_rejection_is_distinct_from_an_uncertain_timeout(self):
        self.opener.open.side_effect = HTTPError("http://ha.invalid", 403, "Forbidden", {}, None)
        self.assertEqual(server.run_routine("morning")[1], "rejected")
        server.routine_last_attempts.clear()
        self.opener.open.side_effect = TimeoutError()
        self.assertEqual(server.run_routine("morning")[1], "unverified")

    def test_legacy_result_stays_readable_during_cutover(self):
        self.respond(lambda _: {"status": "unverified", "steps": {
            "lounge_wall_lights": "confirmed", "dining_lights": "unverified",
        }})
        reply, outcome, detail = server.run_routine("morning")
        self.assertEqual(outcome, "unverified")
        self.assertIn("lounge wall lights are on", reply)
        self.assertIn("dining light level", detail)
