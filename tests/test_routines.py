"""Verify the request contract and reported routine outcomes."""

import io
import json
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError

import server

from test_home_assistant import HA_ENV


class RoutineTests(TestCase):
    def setUp(self):
        self.enterContext(patch.dict(server.os.environ, HA_ENV | {
            "DECLAN_MOVIE_SCRIPT": "script.movie", "DECLAN_MOVIE_REMOTE": "remote.projector",
        }))
        self.enterContext(patch.object(server, "routine_last_attempts", {}))
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

    def test_movie_app_launch_requires_verified_routine(self):
        self.respond(lambda data: self.confirmed(data, outcome="partial", resolved_action="start"))
        steps = []
        reply, outcome, _ = server.run_routine("movie", movie_action="start",
                                               movie_app=server.MOVIE_APPS["netflix"], action_results=steps)
        self.assertEqual(outcome, "partial")
        self.assertEqual(steps[-1]["status"], "skipped")
        self.assertEqual(len(self.calls), 1)
        server.routine_last_attempts.clear()
        self.respond(lambda data: self.confirmed(data, resolved_action="start"))
        reply, outcome, _ = server.run_routine("movie", movie_action="start",
                                               movie_app=server.MOVIE_APPS["netflix"], action_results=steps)
        self.assertEqual(outcome, "partial")
        self.assertIn("couldn't verify the app is on screen", reply)
        self.assertEqual(json.loads(self.calls[-1].data)["command"], "app:netflix")

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
