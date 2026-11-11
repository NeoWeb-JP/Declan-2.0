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
            {"entity_id": "input_text.guests_in_charge", "state": ""},
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
            if 'declan_inventory_page' in data['template']:
                rows = [dict(row, attributes=row.get('attributes', {})) for row in self.entities.values()
                        if row['entity_id'].partition('.')[0] in server.ha_inventory.DEVICE_DOMAINS]
                result = {'total': len(rows), 'rows': rows}
            else:
                result = self.areas[:1] if "area_id(" in data["template"] else self.areas
        elif path == "/api/":
            result = {"message": "API running."}
        elif path in {"/api/services/input_text/set_value", "/api/services/input_boolean/turn_off"}:
            if self.apply:
                self.entities[data["entity_id"]]["state"] = data.get("value", "off")
            result = []
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

    def test_exclusion_with_except_for_and_room_alias(self):
        self.ha.entities["light.study_light"]["state"] = "on"
        self.run_light("turn everything off except for the office", "confirmed")
        self.assertEqual(self.ha.entities["light.study_light"]["state"], "on")
        self.assertEqual(self.ha.entities["light.bedroom_lamp"]["state"], "off")
        self.assertEqual(self.ha.entities["light.lounge_lamp"]["state"], "off")

    def test_room_lights_confirmation_keeps_device_names_in_action_results(self):
        for starting_state in ("on", "off"):
            with self.subTest(starting_state=starting_state):
                steps = []
                reply, outcome = server.handle_light_request(
                    "turn the lounge and the bedroom lights off", action_results=steps,
                )
                self.assertEqual(outcome, "confirmed", reply)
                self.assertTrue(reply.startswith("Done. "), reply)
                self.assertNotIn("Lounge Lamp", reply)
                self.assertNotIn("Bedroom Lamp", reply)
                self.assertEqual({step["status"] for step in steps}, {"confirmed"})

    def test_mixed_room_actions_with_trailing_directions(self):
        self.ha.entities["light.study_light"]["state"] = "on"
        self.ha.entities["light.bedroom_lamp"]["state"] = "off"
        self.run_light("turn the office off and the bedroom on", "confirmed")
        self.assertEqual(self.ha.entities["light.study_light"]["state"], "off")
        self.assertEqual(self.ha.entities["light.bedroom_lamp"]["state"], "on")

    def test_room_off_dispatches_even_when_home_assistant_already_reports_off(self):
        self.run_light("turn the office off and the bedroom on", "confirmed")
        self.assertIn(("/api/services/light/turn_off", {"entity_id": "light.study_light"}), self.ha.calls)

    def test_partial_room_reply_omits_device_list(self):
        self.ha.entities["light.bedroom_lamp"]["state"] = "unavailable"
        steps = []
        reply, outcome = server.handle_light_request(
            "turn the office off and the bedroom on", action_results=steps,
        )
        self.assertEqual(outcome, "partial", reply)
        self.assertIn("I handled part of that.", reply)
        self.assertNotIn("Bedroom Lamp", reply)
        self.assertTrue(any(step["target"] == "Bedroom Lamp" and step["status"] == "skipped" for step in steps))

    def test_brightness_and_pronoun_follow_up(self):
        self.run_light("make the bedroom lamp darker and make the lounge lamp very bright", "confirmed")
        self.assertEqual(self.ha.entities["light.lounge_lamp"]["attributes"]["brightness"], 255)
        self.assertEqual(self.ha.entities["light.bedroom_lamp"]["attributes"]["brightness"], 102)
        self.run_light("set the bedroom lamp to 30 percent", "confirmed")
        self.run_light("turn it off", "confirmed", last_lights=("light.bedroom_lamp",))
        self.run_light("turn it on", "unresolved")
        self.run_light("set the bedroom lamp to 110 percent", "unresolved")

    def test_spoken_lounge_dimming_uses_relative_brightness(self):
        self.ha.areas[-1][0] = "Living Room"
        lamp = self.ha.entities["light.lounge_lamp"]
        for phrase, expected in (
            ("dim the lights in the lounge by 20%", 30),
            ("turn down the lights in the lounge", 20),
            ("make it darker in the lounge", 10),
        ):
            with self.subTest(phrase=phrase):
                self.run_light(phrase, "confirmed")
                self.assertEqual(lamp["attributes"]["brightness"], round(expected * 255 / 100))
        self.assertEqual(self.ha.entities["light.bedroom_lamp"]["attributes"]["brightness"], 128)
        self.run_light("dim the lights in the lounge by 120 percent", "unresolved")

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
        self.ha.fail = "/api/template"
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
    def test_web_voice_discovers_declan_engine_by_name(self):
        with patch.dict(os.environ, HA_ENV | {"DECLAN_WEB_TTS_ENTITY": ""}), patch.object(server, "build_opener") as build:
            opener = build.return_value
            opener.open.side_effect = [
                io.BytesIO(b'[["tts.other_elevenlabs","ElevenLabs"],["tts.house_voice","Declan - South African News"]]'),
                io.BytesIO(b'{"path":"/api/tts_proxy/declan.mp3"}'),
                io.BytesIO(b"audio"),
            ]
            self.assertEqual(server.render_web_voice("Hello"), b"audio")
            self.assertEqual(json.loads(opener.open.call_args_list[1].args[0].data)["engine_id"], "tts.house_voice")

    def test_web_voice_uses_configured_engine_and_local_audio_path(self):
        environment = HA_ENV | {"DECLAN_WEB_TTS_ENTITY": "tts.elevenlabs"}
        with patch.dict(os.environ, environment), patch.object(server, "build_opener") as build:
            opener = build.return_value
            opener.open.side_effect = [io.BytesIO(b'{"path":"/api/tts_proxy/declan.mp3"}'), io.BytesIO(b"audio")]
            self.assertEqual(server.render_web_voice("Hello"), b"audio")
            generate, download = [entry.args[0] for entry in opener.open.call_args_list]
            self.assertEqual(json.loads(generate.data)["engine_id"], "tts.elevenlabs")
            self.assertEqual(download.full_url, "http://ha.invalid/api/tts_proxy/declan.mp3")
            opener.open.side_effect = [io.BytesIO(b'{"path":"//other.invalid/audio.mp3"}')]
            self.assertIsNone(server.render_web_voice("Hello"))

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
                opener.open.side_effect = None
                opener.open.return_value = io.BytesIO(b"[]")
                self.assertEqual(server.search_media("where can i watch dune")[1], "not_configured")

    def test_media_search_discovers_only_an_unambiguous_local_agent(self):
        environment = HA_ENV | {"DECLAN_MEDIA_SEARCH_AGENT": ""}
        agents = ["conversation.house_voice"]
        reply = {"service_response": {"response": {"speech": {"plain": {"speech": "Test result."}}}}}
        with patch.dict(os.environ, environment), patch.object(server, "build_opener") as build:
            opener = build.return_value
            opener.open.side_effect = [io.BytesIO(json.dumps(value).encode()) for value in (agents, reply)]
            self.assertEqual(server.search_media("where can i watch friends"), ("Test result.", "search_result"))
            discovery = opener.open.call_args_list[0].args[0]
            self.assertEqual(urlsplit(discovery.full_url).path, "/api/template")
            self.assertIn("integration_entities('declan_local')", json.loads(discovery.data)["template"])
            self.assertEqual(json.loads(opener.open.call_args.args[0].data), {
                "agent_id": "conversation.house_voice", "text": "where can i watch friends",
            })
            agents.append("conversation.jarvis_local")
            opener.reset_mock()
            opener.open.side_effect = [io.BytesIO(json.dumps(agents).encode())]
            self.assertEqual(server.search_media("where can i watch friends")[1], "not_configured")
            self.assertEqual(opener.open.call_count, 1)

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


class GuestAssignmentTests(TestCase):
    def setUp(self):
        self.ha = FakeHomeAssistant()
        self.connection = ("http://ha.invalid", {}, self.ha)
        self.mode = self.ha.entities[server.GUEST_MODE_ENTITY]
        self.register = self.ha.entities[server.GUEST_REGISTER_ENTITY]

    def test_check_is_read_only_and_uses_personality_only_when_inactive(self):
        reply, outcome = server.guest_assignment("check", self.connection)
        self.assertEqual(outcome, "confirmed")
        self.assertIn("Guest Mode is off.", reply)
        self.assertIn("Tux", reply)
        self.mode["state"] = "on"
        self.register["state"] = "Mike and Kathy"
        self.assertEqual(server.guest_assignment("check", self.connection),
                         ("Currently in charge: Mike and Kathy. Guest Mode is on.", "confirmed"))
        self.register["state"] = "unavailable"
        self.assertEqual(server.guest_assignment("check", self.connection)[1], "unavailable")
        self.assertTrue(all(data is None for _, data in self.ha.calls))

    def test_clear_verifies_register_before_turning_off_guest_mode(self):
        self.mode["state"] = "on"
        self.register["state"] = "Mike and Kathy"
        self.ha.apply = False
        self.assertEqual(server.guest_assignment("clear", self.connection)[1], "unverified")
        self.assertNotIn("/api/services/input_boolean/turn_off", [path for path, _ in self.ha.calls])

        self.ha.apply = True
        self.ha.fail = "/api/services/input_boolean/turn_off"
        self.assertEqual(server.guest_assignment("clear", self.connection)[1], "partial")
        self.assertEqual((self.register["state"], self.mode["state"]), ("", "on"))

        self.ha.fail = None
        self.assertEqual(server.guest_assignment("clear", self.connection)[1], "confirmed")
        self.assertEqual((self.register["state"], self.mode["state"]), ("", "off"))
