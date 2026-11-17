"""Exercise Declan's browser and Assist API with isolated local state."""

import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from time import monotonic, time
from concurrent.futures import ThreadPoolExecutor
from unittest import TestCase
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import server
from declan_ingress import proxy
from personality import LINES

READ_VISITORS_PRESENT = server.read_visitors_present


class APITests(TestCase):
    def setUp(self):
        directory = Path(self.enterContext(TemporaryDirectory()))
        self.enterContext(patch.object(server.history, "DATABASE", directory / "history.sqlite3"))
        self.enterContext(patch.object(server.music, "SPOTIFY_SETTINGS", directory / "spotify-settings.json"))
        self.enterContext(patch.object(server, "SESSIONS", server.OrderedDict()))
        self.enterContext(patch.object(server, "read_guest_mode", return_value="off"))
        self.enterContext(patch.object(server, "read_visitors_present", return_value=False))
        self.enterContext(patch.dict(server.os.environ, {"DECLAN_ASSIST_TOKEN": "test", "DECLAN_ALLOW_UNCONFIGURED_MA": "1"}))
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

    def test_routine_response_editor_reads_saves_and_rejects_stale_edits_without_execution(self):
        item = {"entity_id": "script.good_morning", "name": "Declan - Good Morning", "safe": False}
        headers = {"Origin": self.origin, "Content-Type": "application/json"}
        with patch.object(server.script_discovery, "discover", return_value=([item], None)), \
             patch.object(server.script_discovery, "_execute_provider", side_effect=AssertionError("editor executed a script")), \
             patch.object(server.script_discovery, "_enqueue_provider", side_effect=AssertionError("editor queued a script")):
            code, payload = self.request('/api/native/routine-responses', headers=headers)
            self.assertEqual(code, 200)
            self.assertEqual(json.loads(payload)['routines'][0]['entity_id'], item['entity_id'])
            code, payload = self.request('/api/native/routine-responses', body={'entity_id': item['entity_id']}, headers=headers)
            self.assertEqual(code, 200)
            state = json.loads(payload)
            state['profile']['requested']['sass']['default'] = ['My custom morning response.']
            state['profile']['requested']['guest']['default'] = ['A guest morning response.']
            body = {'entity_id': item['entity_id'], **state}
            code, payload = self.request('/api/native/routine-responses', body=body, headers=headers)
            self.assertEqual(code, 200, payload)
            self.assertTrue(json.loads(payload)['saved'])
            selection = (("auto:script.good_morning", {"_declan_background": True, "_declan_reply_category": "morning"}), None)
            with patch.object(server, 'select_routine_turn', return_value=selection), \
                 patch.object(server.script_discovery, '_enqueue_provider', return_value=('Requested.', 'started', 'job')), \
                 patch.object(server.CAPTURE_ARBITER, 'claim', return_value=True):
                for path in ('/api/chat', '/api/assist'):
                    reply = self.ask('good morning', path=path)
                    self.assertEqual(reply['reply'], 'My custom morning response.')
                    self.assertEqual(reply['outcome'], 'started')
                with patch.object(server, 'read_visitors_present', return_value=None):
                    self.assertEqual(self.ask('good morning')['reply'], 'A guest morning response.')
                chained = (selection[0], 'turn on the study light')
                with patch.object(server, 'select_routine_turn', return_value=chained), \
                     patch.object(server, 'handle_light_request_result', return_value=('The study light failed.', 'failed')):
                    reply = self.ask('good morning and turn on the study light')
                    self.assertIn('My custom morning response.', reply['reply'])
                    self.assertIn('The study light failed.', reply['reply'])
                    self.assertEqual(reply['outcome'], server.chained_outcome('started', 'failed'))
            body['profile']['requested']['sass']['default'] = ['Stale overwrite']
            code, payload = self.request('/api/native/routine-responses', body=body, headers=headers)
            self.assertEqual(code, 400)
            self.assertIn('changed elsewhere', json.loads(payload)['error'])

    def test_response_editor_reports_missing_routines_and_inspection_failure(self):
        headers = {"Origin": self.origin, "Content-Type": "application/json"}
        with patch.object(server.script_discovery, 'discover', return_value=([], None)):
            code, _ = self.request('/api/native/routine-responses', body={'entity_id': 'script.deleted'}, headers=headers)
            self.assertEqual(code, 400)
        with patch.object(server.script_discovery, 'discover', return_value=([], 'unavailable')):
            code, payload = self.request('/api/native/routine-responses', headers=headers)
            self.assertEqual(code, 200)
            catalog = json.loads(payload)
            self.assertEqual(catalog['routines'], [])
            self.assertIn('command:lights_on', {row['entity_id'] for row in catalog['commands']})
            self.assertIn('routine_error', catalog)
            code, payload = self.request('/api/native/routine-responses',
                                         body={'entity_id': 'script.unavailable'}, headers=headers)
            self.assertEqual(code, 503)
            self.assertIn('unavailable', json.loads(payload)['error'])
        code, _ = self.request('/api/native/routine-responses', body={'entity_id': '../bad'}, headers=headers)
        self.assertEqual(code, 400)

    def test_visitor_presence_is_independent_and_validated(self):
        with patch.dict(server.os.environ, {"DECLAN_HA_URL": "http://ha.local",
                                            "DECLAN_HA_TOKEN": "secret"}), patch.object(
            server.configuration, "get", return_value="input_boolean.visitors_present"
        ), patch.object(server, "build_opener") as factory:
            response = Mock()
            response.read.return_value = b'{"state":"on"}'
            factory.return_value.open.return_value.__enter__.return_value = response
            self.assertIs(READ_VISITORS_PRESENT(), True)
            request = factory.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url,
                             "http://ha.local/api/states/input_boolean.visitors_present")
            factory.return_value.open.return_value.__enter__.return_value.read.return_value = b'{"state":"off"}'
            self.assertIs(READ_VISITORS_PRESENT(), False)
            factory.return_value.open.return_value.__enter__.return_value.read.return_value = b'{"state":"unavailable"}'
            self.assertIsNone(READ_VISITORS_PRESENT())
        with patch.dict(server.os.environ, {"DECLAN_HA_URL": "http://ha.local",
                                            "DECLAN_HA_TOKEN": "secret"}), patch.object(
            server.configuration, "get", return_value="input_boolean.visitors_present/evil"
        ), patch.object(server, "build_opener") as factory:
            self.assertIsNone(READ_VISITORS_PRESENT())
            factory.assert_not_called()

    def test_morning_receipt_returns_morning_sass_on_browser_and_assist(self):
        selection = (("auto:script.good_morning", {"_declan_background": True,
                      "_declan_reply_category": "morning"}), None)
        with patch.object(server, "select_routine_turn", return_value=selection), \
             patch.object(server.script_discovery, "_enqueue_provider", return_value=("Routine requested.", "started", "Background job j")), \
             patch.object(server.script_discovery, "_execute_provider", side_effect=AssertionError("blocking call")), \
             patch.object(server.CAPTURE_ARBITER, "claim", return_value=True):
            for path in ("/api/chat", "/api/assist"):
                reply = self.ask("good morning", path=path)
                self.assertEqual(reply["outcome"], "started")
                self.assertTrue(reply["reply"].startswith("Good morning. "))
                self.assertIn(reply["reply"].removeprefix("Good morning. "), server.personality_policy._MORNING_HOME)
                self.assertEqual(reply["routine_status"], "Background job j")

    def test_morning_receipt_failure_is_not_replaced_by_cheerful_acknowledgement(self):
        selection = (("auto:script.good_morning", {"_declan_background": True,
                      "_declan_reply_category": "morning"}), None)
        with patch.object(server, "select_routine_turn", return_value=selection), \
             patch.object(server.script_discovery, "_enqueue_provider", return_value=("Request not confirmed.", "unverified", None)), \
             patch.object(server.personality_policy, "morning_request_reply", side_effect=AssertionError("false acknowledgement")):
            reply = self.ask("good morning")
            self.assertEqual(reply["outcome"], "unverified")
            self.assertEqual(reply["reply"], "Request not confirmed.")

    def test_night_receipt_returns_bedtime_sass_even_with_guest_mode_on(self):
        # Exercise receipt speech when the configured voice policy allows dispatch.
        self.enterContext(patch.dict(server.os.environ, {"DECLAN_SENSITIVE_ROUTINES": "guest"}))
        self.enterContext(patch.object(server.routine_registry, "load", return_value={}))
        selection = (("auto:script.good_night", {"_declan_background": True,
                      "_declan_reply_category": "night"}), None)
        with patch.object(server, "select_routine_turn", return_value=selection), \
             patch.object(server.script_discovery, "_enqueue_provider", return_value=("Routine requested.", "started", "Background job j")) as enqueue, \
             patch.object(server.script_discovery, "_execute_provider", side_effect=AssertionError("blocking call")), \
             patch.object(server.CAPTURE_ARBITER, "claim", return_value=True):
            for guest in ("off", "on"):
                with patch.object(server, "read_guest_mode", return_value=guest):
                    for path in ("/api/chat", "/api/assist"):
                        reply = self.ask("goodnight", path=path)
                        self.assertEqual(reply["outcome"], "started")
                        self.assertTrue(reply["reply"].startswith("Good night. "))
                        lines = server.personality_policy._NIGHT_GUEST if guest == "on" else server.personality_policy._NIGHT_HOME
                        self.assertIn(reply["reply"].removeprefix("Good night. "), lines)
                        self.assertNotIn("Sorted", reply["reply"])
                        self.assertEqual(reply["routine_status"], "Background job j")
        self.assertEqual(enqueue.call_count, 4)

    def test_night_configured_voice_confirmation_still_precedes_dispatch(self):
        selection = (("auto:script.good_night", {"_declan_background": True,
                      "_declan_reply_category": "night"}), None)
        with patch.dict(server.os.environ, {"DECLAN_SENSITIVE_ROUTINES": "night,guest"}), \
             patch.object(server.routine_registry, "load", return_value={}), \
             patch.object(server, "select_routine_turn", return_value=selection), \
             patch.object(server.script_discovery, "_enqueue_provider", return_value=("Routine requested.", "started", "Background job j")) as enqueue, \
             patch.object(server.CAPTURE_ARBITER, "claim", return_value=True):
            prompt = self.ask("goodnight", path="/api/assist")
            self.assertEqual(prompt["outcome"], "confirmation_prompt")
            enqueue.assert_not_called()
            accepted = self.ask("yes", session=prompt["session_id"], path="/api/assist")
            self.assertEqual(accepted["outcome"], "started")
            self.assertTrue(accepted["reply"].startswith("Good night. "))
            enqueue.assert_called_once()

    def test_night_busy_or_unverified_receipt_never_claims_bedtime_started(self):
        selection = (("auto:script.good_night", {"_declan_background": True,
                      "_declan_reply_category": "night"}), None)
        with patch.object(server, "select_routine_turn", return_value=selection), \
             patch.object(server.personality_policy, "night_request_reply", side_effect=AssertionError("false acknowledgement")):
            for outcome in ("busy", "unverified", "failed"):
                with patch.object(server.script_discovery, "_enqueue_provider", return_value=("Request not accepted.", outcome, None)):
                    reply = self.ask("goodnight")
                    self.assertEqual(reply["outcome"], outcome)
                    self.assertEqual(reply["reply"], "Request not accepted.")

    def test_sexy_receipt_returns_directional_sass_without_waiting_for_music(self):
        with patch.object(server.script_discovery, "_enqueue_provider", return_value=("Routine requested.", "started", "Background job j")) as enqueue, \
             patch.object(server.script_discovery, "_execute_provider", side_effect=AssertionError("blocking music call")), \
             patch.object(server.CAPTURE_ARBITER, "claim", return_value=True):
            for action in ("start", "end"):
                selection = (("auto:script.sexy_time", {"operation": action, "_declan_background": True,
                              "_declan_reply_category": "sexy"}), None)
                with patch.object(server, "select_routine_turn", return_value=selection):
                    for path in ("/api/chat", "/api/assist"):
                        reply = self.ask(action + " bedroom mood", path=path)
                        self.assertEqual(reply["outcome"], "started")
                        self.assertIn(reply["reply"], server.personality_policy._SEXY_HOME[action])
                        self.assertNotIn("Bedroom mood requested", reply["reply"])
                        self.assertNotIn("Bedroom reset requested", reply["reply"])
                        self.assertEqual(reply["routine_status"], "Background job j")
        self.assertEqual(enqueue.call_count, 4)

    def test_sexy_receipt_failure_does_not_get_an_optimistic_reply(self):
        selection = (("auto:script.sexy_time", {"operation": "start", "_declan_background": True,
                      "_declan_reply_category": "sexy"}), None)
        with patch.object(server, "select_routine_turn", return_value=selection), \
             patch.object(server.personality_policy, "sexy_request_reply", side_effect=AssertionError("false acknowledgement")):
            for outcome in ("busy", "unverified", "not_configured", "failed"):
                with patch.object(server.script_discovery, "_enqueue_provider", return_value=("Request not accepted.", outcome, None)):
                    reply = self.ask("bedroom mood")
                    self.assertEqual(reply["outcome"], outcome)
                    self.assertEqual(reply["reply"], "Request not accepted.")

    def test_home_assistant_ingress_enforces_both_boundaries(self):
        token = "x" * 64
        self.enterContext(patch.dict(server.os.environ, {"DECLAN_INGRESS_TOKEN": token}))
        self.enterContext(patch.object(proxy, "SUPERVISOR_ADDRESS", "127.0.0.1"))
        gateway = self.enterContext(proxy.ThreadingHTTPServer(("127.0.0.1", 0), proxy.ProxyHandler))
        gateway.target = urlsplit(self.origin)
        gateway.ingress_token = token
        gateway.panel_token = "p" * 64
        worker = Thread(target=gateway.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(worker.join)
        self.addCleanup(gateway.shutdown)
        origin = f"http://127.0.0.1:{gateway.server_port}"

        def request(path, *, body=None, site=None, panel=None):
            headers = {"Content-Type": "application/json"}
            if panel:
                headers["X-Declan-Panel-Token"] = panel
            if site:
                headers["Sec-Fetch-Site"] = site
            data = json.dumps(body).encode() if body is not None else None
            try:
                with urlopen(Request(origin + path, data=data, headers=headers), timeout=4) as response:
                    return response.status, response.read()
            except HTTPError as error:
                with error:
                    return error.code, error.read()

        self.assertEqual(request("/")[0], 404)
        self.assertEqual(request("/api/chat", body={"message": "hello"}, site="cross-site")[0], 403)
        self.assertEqual(request("/api/assist", body={"message": "hello"}, site="same-origin")[0], 404)
        self.assertEqual(self.request("/api/chat", body={"message": "hello"}, headers={
            "X-Declan-Ingress-Token": "wrong", "Content-Type": "application/json",
        })[0], 403)
        self.assertEqual(request("/api/chat", body={"message": "hello"}, site="same-origin")[0], 200)
        self.assertEqual(request("/api/chat", body={"message": "hello"})[0], 403)
        self.assertEqual(request("/api/chat", body={"message": "hello"}, panel="wrong")[0], 403)
        self.assertEqual(request("/api/chat", body={"message": "hello"}, panel=gateway.panel_token)[0], 200)
        self.assertEqual(request("/api/chat", body={"message": "hello"}, site="cross-site",
                                 panel=gateway.panel_token)[0], 403)
        self.assertEqual(json.loads(request("/api/history")[1])["turns"][0]["message"], "hello")
        with patch.object(proxy, "SUPERVISOR_ADDRESS", "192.0.2.1"):
            self.assertEqual(request("/")[0], 403)

    def test_unqualified_assist_music_passes_origin_to_playback(self):
        with patch.object(server, "ha_device_connection", return_value=None), patch.object(
            server.music, "_play_provider", return_value=("Playing country music.", "confirmed")
        ) as play:
            result = self.ask("Play country music.", path="/api/assist", device="utility-device")
            self.assertEqual(result["outcome"], "confirmed")
            play.assert_called_once_with((None, "country music", "spotify"), None,
                                         server.read_music_inventory, origin="utility-device")

    def test_stop_everywhere_replies_silently(self):
        rows = [
            {"entity_id": "media_player.everywhere", "state": "playing"},
            {"entity_id": "media_player.kitchen", "state": "playing"},
        ]
        destinations = {"everywhere": "media_player.everywhere", "kitchen": "media_player.kitchen"}
        players = {row["entity_id"]: row for row in rows}
        with patch.object(server, "ha_device_connection", return_value=("http://ha", {}, Mock())), patch.object(
            server, "read_music_inventory", return_value=(rows, None)
        ), patch.object(server.music, "music_players", return_value=(destinations, players)), patch.object(
            server.music, "request") as request, patch.object(
            server.music, "wait_for", return_value=True
        ):
            result = self.ask("stop", path="/api/assist", device="bedroom")
            self.assertEqual((result["reply"], result["outcome"]), ("", "confirmed"))
            self.assertEqual(request.call_count, 2)
            self.assertEqual(server.history.recent(limit=1)[0]["reply"], "")

    def test_two_satellites_execute_and_record_one_command(self):
        self.enterContext(patch.object(server, "CAPTURE_ARBITER", server.CaptureArbiter(window=0.03)))
        end = time()
        def call(satellite, rms):
            status, payload = self.request("/api/assist", body={
                "message": "dinner time", "satellite_id": "assist_satellite." + satellite,
                "capture": {"ended_at": end, "duration": 2, "rms": rms},
            }, headers={"Authorization": "Bearer test", "Content-Type": "application/json"})
            self.assertEqual(status, 200)
            return json.loads(payload)
        from execution_results import ExecutionResult, Outcome
        with patch.object(server, "select_routine", return_value=("auto:script.dinner", {})), \
             patch.object(server.script_discovery, "execute_result",
                          return_value=(ExecutionResult("Dinner ready.", Outcome.REQUESTED), None)) as dinner:
            with ThreadPoolExecutor(max_workers=2) as pool:
                quiet = pool.submit(call, "kitchen", 0.1)
                loud = pool.submit(call, "bedroom", 0.5)
                self.assertEqual(sorted((quiet.result()["reply"], loud.result()["reply"])), ["", "Dinner ready."])
            dinner.assert_called_once()
            self.assertEqual(len(server.history.recent()), 1)

    def test_status_and_assets(self):
        with patch.object(server, "RELEASE_VERSION", "v1.2.3"), patch.object(
            server, "home_assistant_status", return_value="disconnected"
        ):
            status, data = self.request("/api/ha-status")
        self.assertEqual((status, json.loads(data)), (200, {"status": "disconnected", "release_version": "v1.2.3"}))
        self.assertEqual(self.request("/")[0], 404)
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

    def test_sexy_time_uses_ha_script_discovery_and_records_history(self):
        script = {"entity_id": "script.declan_sexy_time_controller",
                  "name": "Declan - Sexy Time Controller", "safe": True,
                  "fields": ["operation"]}
        connection = ("http://ha.invalid", {}, Mock())
        with patch.object(server, "ha_device_connection", return_value=connection), \
             patch.object(server.script_discovery, "discover", return_value=([script], None)), \
             patch.object(server.script_discovery, "_enqueue_provider",
                          return_value=("Routine requested.", "started", "Background job j")) as enqueue:
            for phrase, operation in server.SEXY_TIME_COMMANDS.items():
                result = self.ask(phrase, path="/api/assist")
                self.assertEqual(result["outcome"], "started")
                self.assertIn(result["reply"], server.personality_policy._SEXY_HOME[operation])
                self.assertEqual(enqueue.call_args.args[2]["operation"], operation)
                self.assertEqual(server.history.recent(limit=1)[0]["reply"], result["reply"])

    def test_dinner_phrases_use_ha_discovery_and_record_spoken_reply(self):
        script = {"entity_id": "script.declan_dinner_is_served_2",
                  "name": "Declan - Dinner Is Served", "safe": True,
                  "fields": ["dinner_message"]}
        with patch.object(server, "ha_device_connection", return_value=("http://ha.invalid", {}, Mock())), \
             patch.object(server.script_discovery, "discover", return_value=([script], None)), \
             patch.object(server.script_discovery, "_execute_provider",
                          return_value=("Dinner ready.", "requested", None)) as execute:
            for phrase in {*server.DINNER_PHRASES, "it's dinner time"}:
                result = self.ask(phrase + "!", path="/api/assist")
                self.assertEqual(result["outcome"], "requested")
                self.assertEqual(result["reply"], "Dinner ready.")
                self.assertEqual(execute.call_args.args[1]["entity_id"], script["entity_id"])
                self.assertEqual(server.history.recent(limit=1)[0]["reply"], result["reply"])

    def test_guest_commands_record_the_reply_returned_to_assist(self):
        with patch.object(server, "guest_assignment", return_value=("Guest reply.", "confirmed")) as guest:
            for phrase, operation in server.GUEST_COMMANDS.items():
                guest.reset_mock()
                result = self.ask(phrase + "?", path="/api/assist")
                if operation != "check":
                    self.assertEqual(result["outcome"], "confirmation_prompt")
                    guest.assert_not_called()
                    continue
                self.assertEqual(result["reply"], "Guest reply.")
                self.assertEqual(guest.call_args.args[0], operation)
                turn = server.history.recent(limit=1)[0]
                self.assertEqual((turn["source"], turn["reply"]), ("assist", result["reply"]))

    def test_teach_and_forget_a_missed_voice_intention(self):
        path = "/api/history/intents"
        headers = {"Origin": self.origin, "Content-Type": "application/json"}
        script = {"entity_id": "script.declan_sexy_time_controller",
                  "name": "Declan - Sexy Time Controller", "safe": True,
                  "fields": ["operation"]}
        with patch.object(server, "ha_device_connection", return_value=("http://ha.invalid", {}, Mock())), \
             patch.object(server.script_discovery, "discover", return_value=([script], None)), \
             patch.object(server.script_discovery, "_enqueue_provider",
                          return_value=("Routine requested.", "started", "Background job j")) as routine:
            self.assertEqual(self.ask("Finish bedroom session.", path="/api/assist")["reply"], server.UNMATCHED_REPLY)
            turn = json.loads(self.request("/api/history")[1])["turns"][0]
            self.assertTrue(turn["teachable"])
            correction = {"turn_id": turn["id"], "target": "end sexy time"}
            self.assertEqual(self.request(path, body=correction, headers={**headers, "Origin": "https://else.invalid"})[0], 403)
            self.assertEqual(self.request(path, body={**correction, "target": ""}, headers=headers)[0], 400)
            self.assertEqual(self.request(path, body=correction, headers=headers)[0], 200)
            routine.assert_not_called()
            accepted = self.ask("FINISH BEDROOM SESSION!", path="/api/assist")
            self.assertEqual(accepted["outcome"], "started")
            self.assertIn(accepted["reply"], server.personality_policy._SEXY_HOME["end"])
            self.assertEqual(routine.call_args.args[2]["operation"], "end")
            self.assertEqual(server.history.recent(limit=1)[0]["message"], "FINISH BEDROOM SESSION!")
            self.assertEqual(self.request(path, body={"forget": "finish bedroom session"}, headers=headers)[0], 200)
            self.assertEqual(self.ask("finish bedroom session", path="/api/assist")["reply"], server.UNMATCHED_REPLY)
            routine.assert_called_once()

    def test_free_text_correction_uses_normal_time_handler_and_preserves_transcript(self):
        self.ask("Bring me time!", path="/api/assist")
        turn = server.history.recent(limit=1)[0]
        headers = {"Origin": self.origin, "Content-Type": "application/json"}
        correction = {"turn_id": turn["id"], "target": "What is the time?"}
        self.assertEqual(self.request("/api/history/intents", body=correction, headers=headers)[0], 200)
        self.assertEqual(len(server.history.recent()), 1)
        result = self.ask("Bring me time!", path="/api/assist")
        self.assertIn("It's ", result["reply"])
        self.assertEqual(server.history.recent(limit=1)[0]["message"], "Bring me time!")
        with self.assertRaises(ValueError):
            server.history.teach_intent(turn["id"], "Bring me time!", server.UNMATCHED_REPLY)

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
        self.assertIn("here", self.ask("What's the time?", session)["reply"])
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
        with patch.object(server.music, "_play_provider", return_value=("Spotify is playing everywhere.", "confirmed")) as play:
            response = self.ask("Move the music everywhere", path="/api/assist")
        self.assertEqual(response["outcome"], "confirmed")
        self.assertEqual(play.call_args.args[0], ("everywhere", None, "spotify"))

    def test_room_music_stop_routes_to_transport_control(self):
        with patch.object(server.music, "_control_provider", return_value=server.music.music_execution_result(("Stopped playback in the bedroom.", "confirmed"))) as control:
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
        self.enterContext(patch.object(server.history, "initialize"))
        http = self.enterContext(patch.object(server, "ThreadingHTTPServer"))
        host = http.return_value
        host.server_port = 8765
        worker = self.enterContext(patch.object(server, "Thread")).return_value
        worker.is_alive.side_effect = [True, False]
        opener = self.enterContext(patch.object(server, "build_opener")).return_value
        opener.open.return_value = io.BytesIO(b'{"status":"ok"}')
        ring = self.enterContext(patch.object(server.timers, "ring_due", side_effect=OSError()))
        prune = self.enterContext(patch.object(server.history, "prune", side_effect=OSError()))
        self.enterContext(patch("sys.argv", ["server.py"]))
        stdout = self.enterContext(patch("sys.stdout", new_callable=io.StringIO))
        with self.assertLogs(level="ERROR") as logs:
            server.main()
        http.assert_called_once_with(("127.0.0.1", 8765), server.Handler)
        opener.open.assert_called_once_with("http://127.0.0.1:8765/health", timeout=3)
        ring.assert_called_once_with(opener)
        prune.assert_called_once()
        host.shutdown.assert_called_once()
        self.assertIn("Timer alarms could not be checked.", '\n'.join(logs.output))

    def test_every_background_job_isolated_and_retried_after_unexpected_errors(self):
        self.enterContext(patch.object(server.history, "initialize"))
        host = self.enterContext(patch.object(server, "ThreadingHTTPServer")).return_value
        host.server_port = 8765
        worker = self.enterContext(patch.object(server, "Thread")).return_value
        worker.is_alive.side_effect = [True, True, False]
        opener = self.enterContext(patch.object(server, "build_opener")).return_value
        opener.open.return_value = io.BytesIO(b'{"status":"ok"}')
        self.enterContext(patch.object(server, "monotonic", side_effect=iter(range(0, 40000, 4000))))
        self.enterContext(patch.object(server, "ha_device_connection", return_value=None))
        ring = self.enterContext(patch.object(server.timers, "ring_due", side_effect=[KeyError(), None]))
        music = self.enterContext(patch.object(server.music, "skip_blocked_tracks", side_effect=[ValueError(), None]))
        prune = self.enterContext(patch.object(server.history, "prune", side_effect=[TypeError(), None]))
        self.enterContext(patch("sys.argv", ["server.py"]))
        with self.assertLogs(level="ERROR") as logs:
            server.main()
        self.assertEqual((ring.call_count, music.call_count, prune.call_count), (2, 2, 2))
        self.assertEqual(len(logs.output), 3)
        host.shutdown.assert_called_once()

    def test_learned_intent_database_failure_is_logged(self):
        import sqlite3
        # Reuse the HTTP fixture to check the actual request error path.
        fixture = APITests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        with patch.object(server.history, 'learned_intent', side_effect=sqlite3.OperationalError('locked')), patch.object(
                server.Handler, 'log_error') as log:
            response = fixture.ask('hello', path='/api/assist')
            self.assertIsInstance(response['reply'], str)
        log.assert_called_once_with('Could not look up learned intention; using the original transcript.')


