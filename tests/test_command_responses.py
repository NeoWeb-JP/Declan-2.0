"""Exercise everyday edits through authenticated handlers and actual reply selection."""
import copy
import io
import json
import tempfile
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

import command_responses as commands
import history
import personality
import server


class CommandResponseTests(TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(history, "DATABASE", Path(directory) / "history.db"))
        self.row = commands.item("command:lights_on")

    def save(self, home, guest, failure=None):
        state = commands.snapshot(self.row)
        profile = state["profile"]
        profile["completed"]["sass"]["default"] = home
        profile["completed"]["guest"]["default"] = guest
        profile["failure"]["sass"]["default"] = failure or []
        commands.save(self.row, profile, state["expected"])
        return profile

    def handler(self, method, body=None, *, authorised=True, remote=False):
        handler = object.__new__(server.Handler)
        handler.path = "/api/native/routine-responses"
        handler.headers = Message()
        handler.headers["Host"] = "declan.internal:52737"
        handler.headers["Authorization"] = "Bearer " + ("x" * 32 if authorised else "wrong")
        handler.client_address = ("192.0.2.10" if remote else "127.0.0.1", 1)
        handler.server = SimpleNamespace(server_port=52737)
        handler.has_ingress_access = lambda: False
        handler.send_json = Mock()
        handler.log_error = Mock()
        if body is not None:
            encoded = json.dumps(body).encode()
            handler.headers["Content-Type"] = "application/json"
            handler.headers["Content-Length"] = str(len(encoded))
            handler.rfile = io.BytesIO(encoded)
        with patch.dict(server.os.environ, {"DECLAN_ASSIST_TOKEN": "x" * 32}):
            (handler.do_GET if method == "GET" else handler.handle_post)()
        return handler.send_json.call_args.args

    def test_catalog_stays_editable_without_ha_and_rejects_remote_without_token(self):
        with patch.object(server.script_discovery, "discover_result", return_value=server.script_discovery.DiscoveryResult(tuple([]), server.script_discovery.DiscoveryError.INSPECTION_UNAVAILABLE)):
            status, catalog = self.handler("GET", remote=True)
        self.assertEqual(status, 200)
        self.assertIn(self.row["entity_id"], {row["entity_id"] for row in catalog["commands"]})
        self.assertEqual(catalog["routines"], [])
        self.assertIn("routine_error", catalog)
        self.assertEqual(self.handler("GET", authorised=False, remote=True)[0], 403)
        self.assertEqual(self.handler("POST", self.row, authorised=False, remote=True)[0], 403)

    def test_authenticated_edits_persist_without_discovery_or_action_dispatch(self):
        with patch.object(server.script_discovery, "discover_result", side_effect=AssertionError("Must not need HA")), patch.object(server, "set_lights") as dispatch:
            status, state = self.handler("POST", self.row, remote=True)
            self.assertEqual(status, 200)
            state["profile"]["completed"]["sass"]["default"] = ["Custom one", "Custom two"]
            payload = {**self.row, **state}
            self.assertTrue(self.handler("POST", payload, remote=True)[1]["saved"])
            self.assertEqual(self.handler("POST", payload, remote=True)[0], 400)
            dispatch.assert_not_called()
        lines = [personality.add_sass("Study is on.", "lights_on", "off") for _ in range(8)]
        self.assertEqual(set(lines), {"Custom one Study is on.", "Custom two Study is on."})
        self.assertTrue(all(left != right for left, right in zip(lines, lines[1:])))
        history._initialized.clear()
        self.assertEqual(commands.snapshot(self.row)["profile"], state["profile"])

    def test_guest_unknown_and_empty_lists_never_use_home_banter(self):
        self.save(["Private home line"], ["Guest line"])
        self.assertEqual(personality.add_sass("Study is on.", "lights_on", "on"), "Guest line Study is on.")
        self.assertEqual(personality.add_sass("Study is on.", "lights_on", None), "Guest line Study is on.")
        self.save([], [])
        self.assertEqual(personality.add_sass("Study is on.", "lights_on", "off"), "Study is on.")
        self.assertEqual(commands.selected("lights_off", False), None)
        self.assertEqual(commands.selected("not_a_category", False), None)

    def test_failure_addition_cannot_remove_real_error_or_change_outcome(self):
        self.save(["Success line"], ["Guest line"], ["Oh dear."])
        self.assertEqual(commands.failure("lights_on", "HA rejected the light.", guest=False),
                         "Oh dear. HA rejected the light.")
        self.assertEqual(commands.failure("lights_on", "HA rejected the light.", guest=True),
                         "HA rejected the light.")
        self.assertNotIn("Success line", commands.failure("lights_on", "Not verified.", guest=False))

    def test_validation_and_stale_writes_leave_saved_profile_unchanged(self):
        state = commands.snapshot(self.row)
        for mutate in (
            lambda p: p["completed"]["sass"].update(default=["same", " same "]),
            lambda p: p["completed"]["sass"].update(default=["bad\\x00".replace("\\x00", "\x00")]),
            lambda p: p["requested"]["sass"].update(default=["Early success"]),
            lambda p: p["completed"]["sass"].update(start=["Unsupported slot"]),
        ):
            profile = copy.deepcopy(state["profile"])
            mutate(profile)
            with self.assertRaises(ValueError):
                commands.save(self.row, profile, state["expected"])
            self.assertEqual(commands.snapshot(self.row), state)
        for entity in ("script.any", "command:unknown", "command:../x", None):
            with self.assertRaises(ValueError):
                commands.item(entity)

    def test_real_lighting_dispatch_uses_custom_lines_and_keeps_factual_results(self):
        from test_home_assistant import FakeHomeAssistant, HA_ENV
        ha = FakeHomeAssistant()
        self.save(["On custom"], ["Guest custom"])
        for category, phrase, expected in (
            ("lights_on", "turn study light on", "On custom"),
            ("lights_off", "turn study light off", "Off custom"),
            ("brightness", "set bedroom lamp to 30 percent", "Brightness custom"),
        ):
            row = commands.item("command:" + category)
            state = commands.snapshot(row)
            state["profile"]["completed"]["sass"]["default"] = [expected]
            commands.save(row, state["profile"], state["expected"])
            with patch.dict(server.os.environ, HA_ENV), patch.object(server, "build_opener", return_value=ha):
                result, outcome = server.handle_light_request(phrase)
            self.assertEqual(outcome, "confirmed")
            self.assertIn(expected, result)
            self.assertRegex(result, r"is (?:on|off)|at 30%")
        self.assertEqual(ha.entities["light.study_light"]["state"], "off")

    def test_request_history_uses_custom_reply_once_and_failure_never_uses_success(self):
        self.save(["Custom light line"], ["Guest light line"], ["A lighting problem."])
        for phrase, result in (
            ("turn study light on", ("Custom light line Study is on.", "confirmed")),
            ("turn study light on", ("Home Assistant rejected Study.", "action_error")),
            ("preview turn study light on", ("Preview only.", "preview")),
        ):
            handler = object.__new__(server.Handler)
            handler.path = "/api/assist"
            handler.headers = Message()
            encoded = json.dumps({"message": phrase, "device_id": "kitchen"}).encode()
            for key, value in {"Authorization":"Bearer test", "Content-Type":"application/json",
                               "Content-Length":str(len(encoded))}.items():
                handler.headers[key] = value
            handler.rfile = io.BytesIO(encoded)
            handler.server = SimpleNamespace(bad_tokens=SimpleNamespace(check=lambda *args: 0))
            handler.client_address = ("127.0.0.1",1)
            handler.send_json = Mock()
            handler.log_error = Mock()
            with patch.dict(server.os.environ, {"DECLAN_ASSIST_TOKEN":"test"}), \
                 patch.object(server, "read_guest_mode", return_value="off"), \
                 patch.object(server, "read_visitors_present", return_value=False), \
                 patch.object(server, 'select_routine_turn_result', return_value=None), \
                 patch.object(server, "handle_light_request_result", return_value=result), \
                 patch.object(server, "search_media", return_value=None):
                handler.handle_post()
            status, reply = handler.send_json.call_args.args
            self.assertEqual(status, 200)
            self.assertEqual(reply["outcome"], result[1])
            if result[1] == "confirmed":
                self.assertEqual(reply["reply"], result[0])
            elif result[1] == "preview":
                self.assertEqual(reply["reply"], "Preview only.")
            else:
                self.assertEqual(reply["reply"], "A lighting problem. " + result[0])
                self.assertNotIn("Custom light line", reply["reply"])
            self.assertEqual(history.recent()[0]["reply"], reply["reply"])
