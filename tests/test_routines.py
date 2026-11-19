"""Verify the request contract and reported routine outcomes."""

from typing import Any
from email.message import Message
import io
import json
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError

import legacy_wire
import server

from test_home_assistant import HA_ENV


class RoutineTests(TestCase):
    def setUp(self):
        self.enterContext(patch.dict(server.os.environ, HA_ENV | {
            "DECLAN_MOVIE_SCRIPT": "script.movie", "DECLAN_MOVIE_REMOTE": "remote.projector",
        }))
        self.enterContext(patch.object(server, "ROUTINE_COOLDOWN", server.routine_cooldown.RoutineCooldown()))
        self.mappings = {key: {"script": script, "phrases": [key], "fields": {}, "sensitive": False} for key, script in {"morning": server.GOOD_MORNING_SCRIPT, "night": server.GOOD_NIGHT_SCRIPT, "movie": "script.movie", "movie_bedroom": "script.movie_bedroom"}.items()}
        self.mappings["movie"]["remote"] = "remote.projector"
        self.mappings["movie_bedroom"]["remote"] = "remote.projector"
        self.enterContext(patch.object(server.routine_registry, "load", side_effect=lambda: self.mappings))
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

    def test_ha_script_names_replace_native_custom_phrases(self):
        scripts = [{"entity_id": "script.wake_the_house", "name": "Wake The House", "safe": True},
                   {"entity_id": "script.bedroom_cinema", "name": "Bedroom Cinema", "safe": True}]
        with patch.object(server, "ha_device_connection", return_value=("url", {}, object())), \
             patch.object(server.script_discovery, "discover_result", return_value=server.script_discovery.DiscoveryResult(tuple(scripts), None)):
            self.assertEqual(legacy_wire.select_routine("wake the house", None),
                             ("auto:script.wake_the_house", {}))
            self.assertEqual(legacy_wire.select_routine("bedroom cinema", None),
                             ("auto:script.bedroom_cinema", {}))

    def test_builtin_sensitive_flag_fails_closed(self):
        self.mappings["morning"]["sensitive"] = True
        self.respond(self.confirmed)
        self.assertEqual(legacy_wire.run_routine("morning")[1], "unresolved")
        self.assertEqual(self.calls, [])
        self.assertEqual(legacy_wire.run_routine("morning", approved=True)[1], "reported_success")

    def test_morning_dispatches_once_and_rejects_duplicate(self):
        self.respond(self.confirmed)
        steps: list[dict[str, Any]]
        steps = []
        self.assertEqual(legacy_wire.run_routine("morning", action_results=steps)[1], "reported_success")
        self.assertIn("/script/declan_good_morning_shared_local_routine?", self.calls[0].full_url)
        self.assertEqual(steps[0]["status"], "confirmed")
        self.assertEqual(legacy_wire.run_routine("morning")[1], "duplicate")
        self.assertEqual(len(self.calls), 1)

    def test_night_private_facts_depend_on_guest_mode(self):
        for guest in ("on", "off"):
            with self.subTest(guest=guest):
                server.ROUTINE_COOLDOWN = server.routine_cooldown.RoutineCooldown()
                self.respond(lambda data: self.confirmed(data, guest_mode=guest, bedtime={
                    "battery_percent": 30, "indoor_temperature": 14,
                }))
                reply, outcome, detail = legacy_wire.run_routine("night")
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
                reply, outcome, detail = legacy_wire.run_routine("movie", movie_action=direction)
                self.assertEqual(outcome, "partial")
                self.assertIn("I couldn't confirm Projector media player.", detail)
                intro = "Starting Movie Time. " if direction == "start" else "Ending Movie Time. "
                self.assertTrue(reply.startswith(intro), reply)
                self.assertNotIn("Projector media player", reply)

    def test_movie_app_launch_does_not_use_unverified_legacy_mapping(self):
        with patch.object(server, "ha_device_connection", return_value=None):
            self.assertIsNone(legacy_wire.select_routine("open netflix in the lounge", "bedroom-satellite"))


    def test_missing_movie_mapping_never_discovers_or_runs(self):
        self.mappings.pop("movie")
        with patch.object(server, "discover_movie_entities") as discover:
            _, outcome, _ = legacy_wire.run_routine("movie", movie_action="start")
        self.assertEqual(outcome, "not_configured")
        self.assertEqual(self.calls, [])
        discover.assert_not_called()

    def test_unverified_movie_response_never_launches_app(self):
        self.respond(lambda _: {"outcome": "success"})
        steps: list[dict[str, Any]]
        steps = []
        _, outcome, _ = legacy_wire.run_routine("movie", movie_action="start",
                                          movie_app=server.MOVIE_APPS["netflix"], action_results=steps)
        self.assertEqual(outcome, "unverified")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(steps[-1]["status"], "skipped")

    def test_movie_accepts_a_matching_result_wrapped_by_script_entity(self):
        self.respond(lambda data: {"script.movie": self.confirmed(data, resolved_action="start")})
        steps: list[dict[str, Any]]
        steps = []
        _, outcome, _ = legacy_wire.run_routine(
            "movie", movie_action="start", movie_app=server.MOVIE_APPS["netflix"], action_results=steps,
        )
        self.assertEqual(outcome, "reported_success")
        self.assertEqual([entry.args for entry in self.delay.call_args_list], [(7,)])
        self.assertEqual(steps[-1]["status"], "sent")

    def test_movie_response_from_another_run_cannot_launch_an_app(self):
        self.respond(lambda data: self.confirmed({**data, "request_id": "wrong"}, resolved_action="start"))
        with patch.object(server, "verify_legacy_lounge_start", return_value=True) as fallback:
            _, outcome, _ = legacy_wire.run_routine("movie", movie_action="start", movie_app=server.MOVIE_APPS["netflix"])
        self.assertEqual(outcome, "unverified")
        self.assertEqual(len(self.calls), 1)
        fallback.assert_not_called()

    def test_bedroom_mapping_does_not_use_lounge_script(self):
        self.mappings.pop("movie_bedroom")
        _, outcome, _ = legacy_wire.run_routine("movie", movie_action="start", movie_room="bedroom")
        self.assertEqual(outcome, "not_configured")
        self.assertEqual(self.calls, [])

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
        self.opener.open.side_effect = HTTPError("http://ha.invalid", 403, "Forbidden", Message(), None)
        self.assertEqual(legacy_wire.run_routine("morning")[1], "rejected")
        server.ROUTINE_COOLDOWN = server.routine_cooldown.RoutineCooldown()
        self.opener.open.side_effect = TimeoutError()
        self.assertEqual(legacy_wire.run_routine("morning")[1], "unverified")

    def test_uncorrelated_legacy_result_cannot_claim_success(self):
        self.respond(lambda _: {"status": "success", "steps": {"lights": "confirmed"}})
        reply, outcome, _ = legacy_wire.run_routine("morning")
        self.assertEqual(outcome, "unverified")
        self.assertIn("did not return a correlated completion result", reply)
