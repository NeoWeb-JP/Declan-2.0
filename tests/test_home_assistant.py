"""Exercise Home Assistant request and verification paths with an in-memory fake."""

import io
import json
import os
from urllib.error import HTTPError
from urllib.parse import urlsplit
from unittest import TestCase
from unittest.mock import patch

import server
import timers


HA_ENV = {"DECLAN_HA_URL": "http://ha.invalid", "DECLAN_HA_TOKEN": "test-only"}


def light(name, state="off", **attributes):
    return {"entity_id": "light." + name, "state": state,
            "attributes": {"friendly_name": name.replace("_", " ").title(), **attributes}}


class FakeHomeAssistant:
    def __init__(self):
        entities = [
            light("study_light"), light("fairy_lights", "on"), light("bedroom_lamp", "on", brightness=128),
            light("lounge_lamp", "on", brightness=128), light("lounge_group", "on", entity_id=["light.lounge_lamp"]),
            light("broken_light", "unavailable"),
            {"entity_id": "input_boolean.guest_mode", "state": "off"},
        ]
        self.entities = {entry["entity_id"]: entry for entry in entities}
        self.areas = [["Study", ["light.study_light"]], ["Bedroom", ["light.bedroom_lamp", "light.fairy_lights"]],
                      ["Lounge", ["light.lounge_lamp", "light.lounge_group"]]]
        self.calls = []
        self.fail = None
        self.apply = True

    def open(self, request, timeout):
        path = urlsplit(request.full_url).path
        data = json.loads(request.data) if request.data else None
        self.calls.append((path, data))
        if path == self.fail:
            raise HTTPError(request.full_url, 503, "Unavailable", {}, None)
        if path == "/api/states":
            result = list(self.entities.values())
        elif path.startswith("/api/states/"):
            result = self.entities[path.removeprefix("/api/states/")]
        elif path == "/api/template":
            result = self.areas[:1] if "area_id(" in data["template"] else self.areas
        elif path == "/api/":
            result = {"message": "API running."}
        elif path.startswith("/api/services/light/"):
            if self.apply:
                entities = data["entity_id"]
                for entity in entities if isinstance(entities, list) else [entities]:
                    self.entities[entity]["state"] = path.rsplit("_", 1)[1]
                    if "brightness_pct" in data:
                        self.entities[entity]["attributes"]["brightness"] = round(data["brightness_pct"] * 255 / 100)
            result = []
        else:
            raise AssertionError(path)
        response = io.BytesIO(json.dumps(result).encode())
        response.status = 200
        return response


class LightingTests(TestCase):
    def setUp(self):
        self.ha = FakeHomeAssistant()
        self.enterContext(patch.dict(os.environ, HA_ENV))
        self.enterContext(patch.object(server, "build_opener", return_value=self.ha))

    def run_light(self, phrase, expected, **kwargs):
        steps = []
        reply, outcome = server.handle_light_request(phrase, action_results=steps, **kwargs)
        self.assertEqual(outcome, expected, reply)
        return steps

    def test_mixed_actions_and_unresolved_target(self):
        steps = self.run_light("turn on the office light and unknown lamp and turn off the fairy lights", "partial")
        self.assertEqual({step["status"] for step in steps}, {"confirmed", "skipped"})
        self.assertEqual(self.ha.entities["light.study_light"]["state"], "on")
        self.assertEqual(self.ha.entities["light.fairy_lights"]["state"], "off")

    def test_exclusion_and_room_selection(self):
        self.run_light("turn everything off except the bedroom", "confirmed")
        self.assertEqual(self.ha.entities["light.lounge_lamp"]["state"], "off")
        self.assertEqual(self.ha.entities["light.bedroom_lamp"]["state"], "on")
        self.assertEqual(self.ha.entities["light.lounge_group"]["state"], "on")
        self.run_light("turn the bedroom off and turn the lounge on", "confirmed")
        self.assertEqual(self.ha.entities["light.bedroom_lamp"]["state"], "off")
        self.assertEqual(self.ha.entities["light.lounge_lamp"]["state"], "on")

    def test_brightness_and_pronoun_follow_up(self):
        self.run_light("make the bedroom lamp darker and make the lounge lamp very bright", "confirmed")
        self.assertEqual(self.ha.entities["light.lounge_lamp"]["attributes"]["brightness"], 255)
        self.assertEqual(self.ha.entities["light.bedroom_lamp"]["attributes"]["brightness"], 102)
        self.run_light("set the bedroom lamp to 30 percent", "confirmed")
        self.run_light("turn it off", "confirmed", last_lights=("light.bedroom_lamp",))
        self.run_light("turn it on", "unresolved")
        self.run_light("set the bedroom lamp to 110 percent", "unresolved")

    def test_contextual_lights_status_and_preview(self):
        self.run_light("turn on some lights in here", "confirmed", origin_device="study-device")
        self.assertEqual(self.ha.entities["light.study_light"]["state"], "on")
        self.run_light("turn on some lights in here", "confirmed", origin_device="study-device")
        self.run_light("turn on some lights in here", "unresolved")
        self.run_light("what lights are on", "partial")
        steps = self.run_light("preview turn off the lounge", "preview")
        self.assertEqual(steps[0]["status"], "planned")
        self.assertEqual(self.ha.entities["light.lounge_lamp"]["state"], "on")

    def test_unverified_and_failed_dispatch(self):
        self.ha.apply = False
        with patch.object(server, "monotonic", side_effect=range(0, 100)):
            steps = self.run_light("turn on the study light", "unverified")
        self.assertEqual(steps[0]["status"], "unverified")
        self.ha.fail = "/api/services/light/turn_on"
        self.assertEqual(self.run_light("turn on the study light", "action_error")[0]["status"], "failed")
        self.ha.fail = "/api/states"
        self.run_light("turn on the study light", "unavailable")

    def test_ambiguity_and_conflicting_actions(self):
        self.ha.entities["light.second"] = light("second", friendly_name="Fairy Lights")
        self.run_light("turn off the fairy lights", "unresolved")
        self.ha.entities.pop("light.second")
        self.run_light("turn on the fairy lights and turn off the fairy lights", "unresolved")
        self.assertFalse(any("/services/" in path for path, _ in self.ha.calls))

    def test_home_assistant_status(self):
        self.assertEqual(server.home_assistant_status(), "connected")
        self.assertEqual(server.read_guest_mode(), "off")
        self.ha.fail = "/api/"
        self.assertEqual(server.home_assistant_status(), "disconnected")


class ServiceTests(TestCase):
    def test_media_search_requires_configured_agent_and_valid_response(self):
        environment = HA_ENV | {"DECLAN_MEDIA_SEARCH_AGENT": "conversation.declan_local"}
        with patch.dict(os.environ, environment), patch.object(server, "build_opener") as build:
            reply = {"speech": {"plain": {"speech": "It's on Netflix."}}, "response_type": "action_done"}
            opener = build.return_value
            opener.open.return_value = io.BytesIO(json.dumps({"service_response": {"response": reply}}).encode())
            self.assertEqual(server.search_media("where can i watch dune"), ("It's on Netflix.", "search_result"))
            request = opener.open.call_args.args[0]
            self.assertEqual(json.loads(request.data)["agent_id"], "conversation.declan_local")
            self.assertEqual(server.search_media("where can i watch dune and turn on the lights")[1], "unresolved")
            opener.open.side_effect = TimeoutError()
            self.assertEqual(server.search_media("where can i watch dune")[1], "unverified")
            with patch.dict(os.environ, {"DECLAN_MEDIA_SEARCH_AGENT": ""}):
                self.assertEqual(server.search_media("where can i watch dune")[1], "not_configured")

    def test_timer_output_requires_one_available_satellite(self):
        with patch.dict(os.environ, HA_ENV | {"DECLAN_BROWSER_TIMER_SATELLITE": "assist_satellite.kitchen"}), patch(
            "timers.ha_json", wraps=timers.ha_json
        ) as request:
            opener = self.enterContext(patch("server.build_opener")).return_value
            opener.open.side_effect = lambda *args, **kwargs: io.BytesIO(
                b'["assist_satellite.kitchen", "Kitchen", "idle"]'
            )
            self.assertEqual(timers.resolve_output(opener, None, None, room="kitchen"),
                             ("assist_satellite.kitchen", "Kitchen"))
            self.assertIn("area_entities", request.call_args.kwargs["data"]["template"])
            self.assertEqual(timers.resolve_output(opener, None, None, browser=True),
                             ("assist_satellite.kitchen", "Kitchen"))
            self.assertIsNone(timers.resolve_output(opener, "bad-id", None))
            self.assertIsNone(timers.resolve_output(opener, None, None))
            self.assertIsNone(timers.resolve_output(opener, "assist_satellite.other", None))
            opener.open.side_effect = HTTPError("http://ha.invalid", 403, "Forbidden", {}, None)
            with self.assertRaisesRegex(ValueError, "rejected"):
                timers.resolve_output(opener, None, "device")
