"""Exercise Declan's browser and Assist API with isolated local state."""

import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from time import monotonic
from unittest import TestCase
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import server


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

    def test_conversation_expiry_and_weather_scope(self):
        session = self.ask("My name is Test Person")["session_id"]
        self.assertIn("Test Person", self.ask("What's my name?", session)["reply"])
        self.assertIn("You said", self.ask("What did I say?", session)["reply"])
        self.assertIn("here", self.ask("What time is it?", session)["reply"])
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
