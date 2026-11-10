"""Exercise Declan's browser and Assist API with isolated local state."""

import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from time import monotonic
from unittest import TestCase
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import server
from declan_ingress import proxy
from personality import LINES


class APITests(TestCase):
    def setUp(self):
        directory = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(patch.object(server.history, "DATABASE", directory / "history.sqlite3"))
        self.enterContext(patch.object(server.music, "SPOTIFY_SETTINGS", directory / "spotify-settings.json"))
        self.enterContext(patch.object(server, "SESSIONS", server.OrderedDict()))
        self.enterContext(patch.object(server, "read_guest_mode", return_value="off"))
        self.enterContext(patch.dict(server.os.environ, {"DECLAN_ASSIST_TOKEN": "test"}))
        http = self.enterContext(server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler))
        worker = Thread(target=http.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(worker.join)
        self.addCleanup(http.shutdown)
        self.origin = f"http://127.0.0.1:{http.server_port}"

    def request(self, path, *, body=None, headers=None):
        request = Request(self.origin + path, data=json.dumps(body).encode() if body is not None else None,
                          headers=headers or {})
        try:
            with urlopen(request, timeout=4) as response:
                return response.status, response.read()
        except HTTPError as error:
            with error:
                return error.code, error.read()

    def ask(self, message, session=None, *, path="/api/chat", device="bedroom"):
        status, result = self.request(path, body={"message": message, "session_id": session, "device_id": device},
                                      headers={"Origin": self.origin, "Content-Type": "application/json",
                                               "Authorization": "Bearer test"})
        self.assertEqual(status, 200, result)
        return json.loads(result)

    def test_home_assistant_ingress_enforces_both_boundaries(self):
        token = "x" * 64
        self.enterContext(patch.dict(server.os.environ, {"DECLAN_INGRESS_TOKEN": token}))
        self.enterContext(patch.object(proxy, "SUPERVISOR_ADDRESS", "127.0.0.1"))
        gateway = self.enterContext(proxy.ThreadingHTTPServer(("127.0.0.1", 0), proxy.ProxyHandler))
        gateway.target = urlsplit(self.origin)
        gateway.ingress_token = token
        worker = Thread(target=gateway.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(worker.join)
        self.addCleanup(gateway.shutdown)
        origin = f"http://127.0.0.1:{gateway.server_port}"

        def request(path, *, body=None, site=None):
            headers = {"Content-Type": "application/json"}
            if site:
                headers["Sec-Fetch-Site"] = site
            data = json.dumps(body).encode() if body is not None else None
            try:
                with urlopen(Request(origin + path, data=data, headers=headers), timeout=4) as response:
                    return response.status, response.read()
            except HTTPError as error:
                with error:
                    return error.code, error.read()

        self.assertIn(b"./logo.png", request("/")[1])
        self.assertEqual(request("/api/chat", body={"message": "hello"}, site="cross-site")[0], 403)
        self.assertEqual(request("/api/assist", body={"message": "hello"}, site="same-origin")[0], 404)
        self.assertEqual(self.request("/api/chat", body={"message": "hello"}, headers={
            "X-Declan-Ingress-Token": "wrong", "Content-Type": "application/json",
        })[0], 403)
        self.assertEqual(request("/api/chat", body={"message": "hello"}, site="same-origin")[0], 200)
        self.assertEqual(json.loads(request("/api/history")[1])["turns"][0]["message"], "hello")
        with patch.object(proxy, "SUPERVISOR_ADDRESS", "192.0.2.1"):
            self.assertEqual(request("/")[0], 403)

    def test_status_and_assets(self):
        with patch.object(server, "RELEASE_VERSION", "v1.2.3"), patch.object(
            server, "home_assistant_status", return_value="disconnected"
        ):
            status, data = self.request("/api/ha-status")
        self.assertEqual((status, json.loads(data)), (200, {"status": "disconnected", "release_version": "v1.2.3"}))
        self.assertIn(b"ha-status", self.request("/")[1])
        self.assertTrue(self.request("/logo.png")[1].startswith(b"\x89PNG"))
        self.assertEqual(json.loads(self.request("/health")[1]), {"status": "ok"})
        self.assertEqual(self.request("/unknown")[0], 404)

    def test_spotify_settings_rotate_without_exposing_credentials(self):
        path = "/api/settings/spotify"
        headers = {"Origin": self.origin, "Content-Type": "application/json"}
        first = {"client_id": "first-id", "client_secret": "first-secret"}
        second = {"client_id": "second-id", "client_secret": "second-secret"}
        with patch.dict(server.os.environ, {"DECLAN_SPOTIFY_CLIENT_ID": "env-id",
                                            "DECLAN_SPOTIFY_CLIENT_SECRET": "env-secret"}):
            self.assertEqual(json.loads(self.request(path)[1]), {"source": "environment"})
            self.assertEqual(self.request(path, body=first, headers=headers | {"Origin": "http://other.test"})[0], 403)
            self.assertEqual(self.request(path, body={"client_id": "first-id"}, headers=headers)[0], 400)
            self.assertEqual(self.request(path, body=first, headers=headers)[0], 200)
            self.assertEqual(self.request(path, body=second, headers=headers)[0], 200)
            self.assertEqual(json.loads(self.request(path)[1]), {"source": "saved"})
            self.assertEqual(server.music.spotify_credentials(), (("second-id", "second-secret"), "saved"))

    def test_rejects_unauthenticated_and_invalid_posts(self):
        self.assertEqual(self.request("/api/assist", body={"message": "hello"})[0], 401)
        self.assertEqual(self.request("/api/chat", body={"message": "hello"})[0], 403)
        self.assertEqual(self.request("/unknown", body={})[0], 404)
        self.assertEqual(self.request("/api/chat", body={}, headers={"Origin": self.origin})[0], 415)
        self.assertEqual(self.request("/api/chat", body={"message": " "},
                                      headers={"Origin": self.origin, "Content-Type": "application/json"})[0], 400)

    def test_history_endpoint_exports_assist_evidence(self):
        headers = {"Content-Type": "application/json", "Authorization": "Bearer test"}
        result = self.request("/api/assist/history", body={"message": "good morning"}, headers=headers)
        self.assertEqual(result[0], 400)
        result = self.request("/api/assist/history", headers=headers, body={
            "message": "good morning", "reply": "Morning", "outcome": "partial",
            "steps": {"dining_lights": "unverified"},
        })
        self.assertEqual(result[0], 200)
        self.ask("hello")
        page = json.loads(self.request("/api/history")[1])
        self.assertEqual(page["turns"][1]["action_results"][0]["status"], "unverified")
        self.assertEqual(len(json.loads(self.request("/api/history/export")[1])["turns"]), 2)
        self.assertEqual(self.request("/api/history?before=0")[0], 400)
        self.assertEqual(self.request("/api/history", headers={"Host": "other.invalid"})[0], 403)

    def test_sexy_time_calls_ha_and_uses_declan_music_and_history(self):
        opener = Mock()
        connection = ("http://ha.invalid", {}, opener)
        with patch.object(server, "ha_device_connection", return_value=connection), patch.object(
            server.music, "play", return_value=("Playback started.", "confirmed")
        ) as play:
            for phrase, operation in server.SEXY_TIME_COMMANDS.items():
                opener.open.return_value = io.BytesIO(json.dumps({"service_response": {
                    "operation": operation, "lighting_ok": True, "music_stopped": operation == "end",
                }}).encode())
                result = self.ask(phrase, path="/api/assist")
                self.assertEqual(result["outcome"], "confirmed")
                request = opener.open.call_args.args[0]
                self.assertEqual(request.full_url,
                                 "http://ha.invalid/api/services/script/declan_sexy_time_controller?return_response")
                self.assertEqual(json.loads(request.data), {"operation": operation})
                self.assertIn(result["reply"], LINES[f"sexy_time_{operation}"][0])
                self.assertEqual(server.history.recent(limit=1)[0]["reply"], result["reply"])
            self.assertEqual(play.call_count, 3)
            play.assert_called_with(("bedroom", "sexy time music", "spotify"), connection, server.read_ha_inventory)

            play.return_value = ("Home Assistant took too long to respond.", "unverified")
            opener.open.return_value = io.BytesIO(b'{"service_response":{"operation":"start","lighting_ok":true}}')
            result = self.ask("sexy time", path="/api/assist")
            self.assertEqual(result["outcome"], "partial")
            self.assertIn(result["reply"], LINES["sexy_time_start"][0])
            self.assertNotIn("Home Assistant", result["reply"])
            turn = server.history.recent(limit=1)[0]
            self.assertEqual(turn["reply"], result["reply"])
            self.assertIn("Home Assistant took too long", turn["routine_status"])
            play.reset_mock()

            opener.open.return_value = io.BytesIO(b'{"service_response":{"operation":"start","lighting_ok":false}}')
            self.assertEqual(self.ask("sexy time", path="/api/assist")["outcome"], "unverified")
            play.assert_not_called()

    def test_dinner_phrases_send_one_ha_request_and_save_the_spoken_reply(self):
        opener = Mock()
        opener.open.return_value = io.BytesIO(b"[]")
        connection = ("http://ha.invalid", {}, opener)
        with patch.object(server, "ha_device_connection", return_value=connection):
            for phrase in {*server.DINNER_PHRASES, "it’s dinner time"}:
                opener.open.reset_mock()
                opener.open.return_value = io.BytesIO(b"[]")
                result = self.ask(phrase + "!", path="/api/assist")
                self.assertEqual(result["outcome"], "requested")
                self.assertIn(result["reply"], LINES["dinner_announcement"][0])
                opener.open.assert_called_once()
                request = opener.open.call_args.args[0]
                self.assertEqual(request.full_url, "http://ha.invalid/api/services/script/turn_on")
                self.assertEqual(json.loads(request.data), {
                    "entity_id": "script.declan_dinner_is_served_2",
                    "variables": {"dinner_message": result["reply"]},
                })
                self.assertEqual(server.history.recent(limit=1)[0]["reply"], result["reply"])

            opener.open.reset_mock()
            opener.open.side_effect = TimeoutError
            result = self.ask("dinner time", path="/api/assist")
            self.assertEqual(result["outcome"], "unverified")
            opener.open.assert_called_once()

    def test_guest_commands_record_the_reply_returned_to_assist(self):
        with patch.object(server, "guest_assignment", return_value=("Guest reply.", "confirmed")) as guest:
            for phrase, operation in server.GUEST_COMMANDS.items():
                result = self.ask(phrase + "?", path="/api/assist")
                self.assertEqual(result["reply"], "Guest reply.")
                self.assertEqual(guest.call_args.args[0], operation)
                turn = server.history.recent(limit=1)[0]
                self.assertEqual((turn["source"], turn["reply"]), ("assist", result["reply"]))

    def test_teach_and_forget_a_missed_voice_intention(self):
        path = "/api/history/intents"
        headers = {"Origin": self.origin, "Content-Type": "application/json"}
        with patch.object(server, "run_sexy_time", return_value=("End routine.", "confirmed", None)) as routine:
            self.assertEqual(self.ask("End 60 time.", path="/api/assist")["reply"], server.UNMATCHED_REPLY)
            turn = json.loads(self.request("/api/history")[1])["turns"][0]
            self.assertTrue(turn["teachable"])
            correction = {"turn_id": turn["id"], "target": "end sexy time"}
            self.assertEqual(self.request(path, body=correction, headers={**headers, "Origin": "https://else.invalid"})[0], 403)
            self.assertEqual(self.request(path, body={**correction, "target": "arbitrary service"}, headers=headers)[0], 400)
            self.assertEqual(self.request(path, body=correction, headers=headers)[0], 200)
            routine.assert_not_called()

            self.assertEqual(self.ask("END  60 TIME!", path="/api/assist")["reply"], "End routine.")
            self.assertEqual(routine.call_args.args[0], "end")
            self.assertEqual(server.history.recent(limit=1)[0]["message"], "END  60 TIME!")
            self.assertEqual(self.ask("end 61 time", path="/api/assist")["reply"], server.UNMATCHED_REPLY)
            self.assertEqual(self.request(path, body={"forget": "end 60 time"}, headers=headers)[0], 200)
            self.assertEqual(self.ask("end 60 time", path="/api/assist")["reply"], server.UNMATCHED_REPLY)
            routine.assert_called_once()

    def test_clear_history_requires_local_confirmation(self):
        self.ask("hello")
        server.history.record("assist-session", "assist", "Time?", "It is noon.")
        path = "/api/history/clear"
        local = {"Origin": self.origin, "Content-Type": "application/json"}
        self.assertEqual(self.request(path, body={"confirm": True},
                                      headers={**local, "Origin": "https://other.invalid"})[0], 403)
        self.assertEqual(self.request(path, body={"confirm": False}, headers=local)[0], 400)
        self.assertEqual(len(server.history.recent()), 2)
        status, body = self.request(path, body={"confirm": True}, headers=local)
        self.assertEqual((status, json.loads(body)), (200, {"deleted": 2}))
        self.assertEqual(json.loads(self.request("/api/history/export")[1])["turns"], [])
        self.ask("hello again")
        self.assertEqual(len(server.history.recent()), 1)

    def test_conversation_expiry_and_weather_scope(self):
        session = self.ask("My name is Test Person")["session_id"]
        self.assertIn("Test Person", self.ask("What's my name?", session)["reply"])
        self.assertIn("You said", self.ask("What did I say?", session)["reply"])
        self.assertIn("here", self.ask("What time is it?", session)["reply"])
        self.assertIn("here", self.ask("What's the time?", session)["reply"])
        self.assertIn("here", self.ask("What’s the time?", session)["reply"])
        self.assertIn("say it another way", self.ask("Something else")["reply"])
        with patch.object(server.conditions, "handle", side_effect=lambda phrase, _: (
            ("Oxford forecast", "confirmed", "weather") if "oxford" in phrase else None
        )) as forecast:
            turn = self.ask("What's the weather in Oxford tomorrow?", path="/api/assist")
            session = turn["session_id"]
            self.assertEqual(self.ask("What about Saturday?", session, path="/api/assist")["outcome"], "confirmed")
            self.assertIn("saturday in oxford", forecast.call_args.args[0])
            self.assertEqual(self.ask("What about Saturday?", session, path="/api/assist", device="other")["outcome"],
                             "unresolved")
            session = self.ask("What's the weather in Oxford tomorrow?", path="/api/assist")["session_id"]
            server.SESSIONS[session]["at"] = monotonic() - server.IDLE_SECONDS - 1
            self.assertEqual(self.ask("What about Saturday?", session, path="/api/assist")["outcome"], "unresolved")

    def test_device_and_timer_route(self):
        states = [{"entity_id": "light.fairy_lights", "state": "on",
                   "attributes": {"friendly_name": "Fairy Lights"}}]
        with patch.object(server, "ha_device_connection", return_value=("url", {}, None)), patch.object(
            server, "read_ha_inventory", return_value=(states, None)
        ):
            turn = self.ask("Is the fairy lights on?")
            self.assertEqual(turn["outcome"], "confirmed")
            states[0]["state"] = "off"
            reply = self.ask("Is it off?", turn["session_id"])
            self.assertIn("Fairy Lights is off", reply["reply"])
        with patch.object(server.timers, "handle", return_value=("Timer set.", "timer_set")):
            self.assertEqual(self.ask("Set a timer for five seconds")["outcome"], "timer_set")

    def test_music_handoff_routes_from_assist(self):
        with patch.object(server.music, "play", return_value=("Spotify is playing everywhere.", "confirmed")) as play:
            response = self.ask("Move the music everywhere", path="/api/assist")
        self.assertEqual(response["outcome"], "confirmed")
        self.assertEqual(play.call_args.args[0], ("everywhere", None, "spotify"))

    def test_room_music_stop_routes_to_transport_control(self):
        with patch.object(server.music, "control", return_value=("Stopped playback in the bedroom.", "confirmed")) as control:
            response = self.ask("Stop music in the bedroom", path="/api/chat")
        self.assertEqual(response["outcome"], "confirmed")
        self.assertEqual(control.call_args.args[0], ("media_stop", "bedroom"))


class StartupTests(TestCase):
    def test_assist_requires_fixed_port_and_bridge_token(self):
        with patch.dict(server.os.environ, {"DECLAN_ASSIST_TOKEN": ""}), patch("sys.stderr", new_callable=io.StringIO):
            for args in (["--port", "-1"], ["--assist-lan", "--port", "0"], ["--assist-lan"]):
                with self.subTest(args=args), patch("sys.argv", ["server.py", *args]), self.assertRaises(SystemExit):
                    server.main()

    def test_startup_checks_health_and_keeps_maintenance_running(self):
        http = self.enterContext(patch.object(server, "ThreadingHTTPServer"))
        host = http.return_value
        host.server_port = 8765
        worker = self.enterContext(patch.object(server, "Thread")).return_value
        worker.is_alive.side_effect = [True, False]
        opener = self.enterContext(patch.object(server, "build_opener")).return_value
        opener.open.return_value = io.BytesIO(b'{"status":"ok"}')
        ring = self.enterContext(patch.object(server.timers, "ring_due", side_effect=OSError()))
        prune = self.enterContext(patch.object(server.history, "prune", side_effect=OSError()))
        browser = self.enterContext(patch.object(server.webbrowser, "open"))
        self.enterContext(patch("sys.argv", ["server.py", "--open"]))
        stdout = self.enterContext(patch("sys.stdout", new_callable=io.StringIO))
        server.main()
        http.assert_called_once_with(("127.0.0.1", 8765), server.Handler)
        opener.open.assert_called_once_with("http://127.0.0.1:8765/health", timeout=3)
        browser.assert_called_once_with("http://127.0.0.1:8765/")
        ring.assert_called_once_with(opener)
        prune.assert_called_once()
        host.shutdown.assert_called_once()
        self.assertIn("Timer alarms could not be checked.", stdout.getvalue())
