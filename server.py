"""Local Declan 2.0 chat prototype. Run with python server.py."""
import argparse
import json
import os
import re
import secrets
import sqlite3
from collections import OrderedDict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
import webbrowser

import history


SESSIONS = OrderedDict()
SESSION_LOCK = Lock()
ROUTINE_LOCKS = {"morning": Lock(), "night": Lock()}
routine_last_attempts = {}
IDLE_SECONDS = 300
ASSIST_PORT = 52737
GOOD_MORNING_SCRIPT = "script.declan_good_morning_shared_local_routine"
GOOD_MORNING_PHRASES = {
    "good morning", "morning", "start the morning routine", "declan test good morning",
}

GOOD_NIGHT_SCRIPT = "script.declan_good_night_shared_local_routine"
GOOD_NIGHT_PHRASES = {
    "good night", "good night declan", "goodnight", "it's bedtime",
    "it’s bedtime", "time for bed", "shut the house down", "start the bedtime routine",
}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def home_assistant_status():
    url = os.environ.get("DECLAN_HA_URL", "").strip().rstrip("/")
    token = os.environ.get("DECLAN_HA_TOKEN", "").strip()
    if not url or not token:
        try:
            if history.has_recent_assist():
                return "assist_recent"
        except (OSError, sqlite3.Error):
            pass
        return "not_configured"
    try:
        parsed = urlsplit(url)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            return "not_configured"
        request = Request(url + "/api/", headers={"Authorization": f"Bearer {token}"})
        opener = build_opener(ProxyHandler({}), NoRedirect())
        with opener.open(request, timeout=3) as response:
            payload = json.loads(response.read(4096))
            if response.status == 200 and payload == {"message": "API running."}:
                return "connected"
    except HTTPError as error:
        status = error.code
        error.close()
        if status in {401, 403}:
            return "authentication_failed"
    except (OSError, ValueError):
        pass
    return "disconnected"


def run_routine(period, default_script):
    """Call the configured Home Assistant routine once and read its result."""
    salutation = f"Good {period}."
    lock = ROUTINE_LOCKS[period]
    url = os.environ.get("DECLAN_HA_URL", "").strip().rstrip("/")
    token = os.environ.get("DECLAN_HA_TOKEN", "").strip()
    script = os.environ.get(f"DECLAN_GOOD_{period.upper()}_SCRIPT", default_script).strip()
    try:
        parsed = urlsplit(url)
        configured = (
            token and parsed.scheme in {"http", "https"} and parsed.hostname
            and not any((parsed.username, parsed.password, parsed.query, parsed.fragment))
            and re.fullmatch(r"script\.[a-z0-9_]+", script)
        )
    except ValueError:
        configured = False
    if not configured:
        return f"{salutation} The Home Assistant connection or routine script isn't configured.", "not_configured", None
    if not lock.acquire(blocking=False):
        return f"The {period} routine request is already in progress.", "busy", None
    try:
        last_attempt = routine_last_attempts.get(period)
        if last_attempt is not None and monotonic() - last_attempt < 30:
            return f"I already sent a {period} request. I haven't sent another.", "duplicate", None
        routine_last_attempts[period] = monotonic()
        service = script.split(".", 1)[1]
        request = Request(
            f"{url}/api/services/script/{service}?return_response",
            data=b"{}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST",
        )
        opener = build_opener(ProxyHandler({}), NoRedirect())
        try:
            with opener.open(request, timeout=20 if period == "night" else 8) as response:
                payload = json.loads(response.read(65536))
        except HTTPError as error:
            code = error.code
            error.close()
            if code in {401, 403, 404}:
                return f"{salutation} Home Assistant couldn't accept the configured routine.", "rejected", None
            return f"{salutation} I couldn't confirm the routine completed. Check its Home Assistant trace.", "unverified", None
        except (OSError, ValueError):
            return f"{salutation} I couldn't confirm the routine completed. Check its Home Assistant trace.", "unverified", None
        result = payload.get("service_response") if isinstance(payload, dict) else None
        status = result.get("status") if isinstance(result, dict) else None
        steps = result.get("steps") if isinstance(result, dict) else None
        greeting = result.get("response") if isinstance(result, dict) else None
        greeting = greeting.strip() if isinstance(greeting, str) else ""
        if period == "morning" and status == "unverified" and isinstance(steps, dict):
            checks = {
                "lounge_wall_lights": ("the lounge wall lights are on", "the lounge wall lights"),
                "dining_lights": ("the dining lights are at ten percent", "the dining light level"),
            }
            confirmed = [phrases[0] for key, phrases in checks.items() if steps.get(key) == "confirmed"]
            unverified = [phrases[1] for key, phrases in checks.items() if steps.get(key) != "confirmed"]
            details = []
            if confirmed:
                details.append("Home Assistant shows " + ", and ".join(confirmed) + ".")
            if unverified:
                details.append("I couldn't confirm " + ", or ".join(unverified) + ".")
            return greeting or salutation, "unverified", " ".join(details)
        if period == "night" and status in (None, "unverified", "success"):
            detail = result.get("routine_status") if isinstance(result, dict) else None
            verified = status == "success"
            fallback = ("Home Assistant reports the routine completed." if verified
                        else "Home Assistant did not confirm the bedtime routine completed.")
            return greeting or salutation, "reported_success" if verified else "unverified", detail or fallback
        if status == "success":
            return greeting or salutation, "reported_success", "Home Assistant reports the routine completed."
        if status == "partial":
            return f"{salutation} Part of the routine failed. Check its Home Assistant trace.", "partial", None
        if status == "failed":
            return f"{salutation} Home Assistant reported a failure in the routine.", "failed", None
        if status == "busy":
            return f"{salutation} Home Assistant reports the routine is already running.", "busy", None
        return f"{salutation} Home Assistant answered, but I couldn't verify the device changes.", "unverified", None
    finally:
        lock.release()


def converse(message, session_id, routine_reply=None):
    now = monotonic()
    while SESSIONS and now - next(iter(SESSIONS.values()))["at"] >= IDLE_SECONDS:
        SESSIONS.popitem(last=False)
    state = SESSIONS.pop(session_id, None)
    if state is None:
        session_id = secrets.token_urlsafe(24)
        state = {"last": None, "name": None}
    command = message.casefold().strip(" .?!")
    name = re.fullmatch(r"my name is ([^\W\d_][\w '\u2019-]{0,39})", message.strip(" .?!"), re.I)
    if routine_reply is not None:
        reply = routine_reply
    elif name:
        state["name"] = name[1].strip()
        reply = f"Nice to meet you, {state['name']}."
    elif command in {"what's my name", "what is my name", "do you remember my name"}:
        reply = f"Your name is {state['name']}." if state["name"] else "I don't know your name yet."
    elif command in {"what did i just say", "what did i say"}:
        reply = f"You said: {state['last']}" if state["last"] else "This is your first message."
    elif command in {"what time is it", "what is the time", "tell me the time"}:
        reply = f"It's {datetime.now().astimezone():%H:%M} here."
    elif command in {"hello", "hi", "hey", "hello declan"}:
        reply = f"Hello, {state['name']}." if state["name"] else "Hello. I'm Declan."
    else:
        reply = "I'm the Declan 2.0 test instance. Try telling me your name or asking the time."
    state.update(last=message, at=now)
    SESSIONS[session_id] = state
    if len(SESSIONS) > 128:
        SESSIONS.popitem(last=False)
    return {"session_id": session_id, "reply": reply}


class Handler(BaseHTTPRequestHandler):
    timeout = 5

    def send_body(self, status, data, content_type, filename=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, status, data):
        self.send_body(status, json.dumps(data).encode(), "application/json")

    def do_GET(self):
        if self.client_address[0] != "127.0.0.1":
            self.send_json(403, {"error": "Local access only."})
            return
        if self.path.startswith("/api/history") and self.headers.get("Host") not in {
            f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"
        }:
            self.send_json(403, {"error": "Open history from the local Declan address."})
            return
        if self.path == "/":
            page = Path(__file__).with_name("index.html").read_bytes()
            self.send_body(200, page, "text/html; charset=utf-8")
        elif self.path == "/health":
            self.send_json(200, {"status": "ok"})
        elif self.path == "/api/ha-status":
            self.send_json(200, {"status": home_assistant_status()})
        elif self.path == "/api/history/export":
            try:
                turns = history.recent(limit=None)
            except (OSError, sqlite3.Error):
                self.send_json(503, {"error": "Conversation history is unavailable."})
                return
            self.send_body(
                200, json.dumps({"turns": list(reversed(turns))}, ensure_ascii=False).encode("utf-8"),
                "application/json", "declan-conversation-history.json",
            )
        elif self.path == "/api/history" or self.path.startswith("/api/history?"):
            try:
                params = parse_qs(urlsplit(self.path).query)
                before = int(params["before"][0]) if "before" in params else None
                if before is not None and not 0 < before < 2**63:
                    raise ValueError
                turns = history.recent(before, limit=51)
            except ValueError:
                self.send_json(400, {"error": "Invalid history cursor."})
                return
            except (OSError, sqlite3.Error):
                self.send_json(503, {"error": "Conversation history is unavailable."})
                return
            self.send_json(200, {"turns": turns[:50], "next": turns[49]["id"] if len(turns) > 50 else None})
        else:
            self.send_json(404, {"error": "Not found."})

    def do_POST(self):
        if self.path in {"/api/assist", "/api/assist/history"}:
            token = os.environ.get("DECLAN_ASSIST_TOKEN", "")
            supplied = self.headers.get("Authorization", "")
            if not token or not secrets.compare_digest(supplied.encode(), f"Bearer {token}".encode()):
                self.send_json(401, {"error": "Invalid bridge credentials."})
                return
        elif self.path != "/api/chat":
            self.send_json(404, {"error": "Not found."})
            return
        elif self.client_address[0] != "127.0.0.1":
            self.send_json(403, {"error": "Local access only."})
            return
        elif self.headers.get("Origin") not in {
            f"http://127.0.0.1:{self.server.server_port}",
            f"http://localhost:{self.server.server_port}",
        }:
            self.send_json(403, {"error": "Send chat from the local Declan page."})
            return
        if self.headers.get_content_type() != "application/json":
            self.send_json(415, {"error": "Send application/json."})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 8192:
                raise ValueError
            body = json.loads(self.rfile.read(size))
            message = body["message"].strip()
            session_id = body.get("session_id")
            if not 0 < len(message) <= 1000:
                raise ValueError
            if session_id is not None and (not isinstance(session_id, str) or len(session_id) > 64):
                raise ValueError
        except (ValueError, TypeError, KeyError, AttributeError):
            self.send_json(400, {"error": "Send a message of 1 to 1,000 characters."})
            return
        if self.path == "/api/assist/history":
            spoken_reply = body.get("reply")
            if not isinstance(spoken_reply, str) or not 0 < len(spoken_reply.strip()) <= 1000:
                self.send_json(400, {"error": "A reply of 1 to 1,000 characters is required."})
                return
            try:
                outcome = body.get("outcome")
                routine_status = body.get("routine_status")
                history.record(
                    session_id or secrets.token_urlsafe(24), "ha_sentence", message, spoken_reply,
                    outcome if isinstance(outcome, str) and len(outcome) <= 64 else None,
                    routine_status if isinstance(routine_status, str) and len(routine_status) <= 1000 else None,
                )
            except (OSError, sqlite3.Error):
                self.send_json(503, {"error": "Conversation history is unavailable."})
                return
            self.send_json(200, {"history_saved": True})
            return
        source = "assist" if self.path == "/api/assist" else (
            "browser_voice" if body.get("source") == "voice" else "browser_keyboard"
        )
        routine_reply = outcome = routine_status = None
        phrase = " ".join(message.casefold().strip(" .?!").split())
        if phrase in GOOD_MORNING_PHRASES:
            routine_reply, outcome, routine_status = run_routine("morning", GOOD_MORNING_SCRIPT)
        elif phrase in GOOD_NIGHT_PHRASES:
            routine_reply, outcome, routine_status = run_routine("night", GOOD_NIGHT_SCRIPT)
        with SESSION_LOCK:
            reply = converse(message, session_id, routine_reply)
            try:
                history.record(reply["session_id"], source, message, reply["reply"], outcome, routine_status)
            except (OSError, sqlite3.Error):
                self.log_error("Could not save conversation history.")
                reply["history_saved"] = False
        self.send_json(200, reply)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--open", action="store_true", help="Open chat in the default browser.")
    parser.add_argument("--assist-lan", action="store_true", help="Allow the authenticated Assist endpoint on the LAN.")
    parser.add_argument("--port", type=int, help="Override the default port (8765, or 52737 in Assist LAN mode).")
    args = parser.parse_args()
    port = args.port if args.port is not None else (ASSIST_PORT if args.assist_lan else 8765)
    if not 0 <= port <= 65535:
        parser.error("--port must be between 0 and 65535.")
    if args.assist_lan and port == 0:
        parser.error("Assist LAN mode needs a fixed port. Omit --port to use 52737.")
    if args.assist_lan and len(os.environ.get("DECLAN_ASSIST_TOKEN", "")) < 32:
        parser.error("--assist-lan requires a DECLAN_ASSIST_TOKEN of at least 32 characters.")
    bind_address = "0.0.0.0" if args.assist_lan else "127.0.0.1"
    try:
        server = ThreadingHTTPServer((bind_address, port), Handler)
    except OSError as error:
        parser.exit(1, f"Declan could not open port {port}: {error}\n")
    with server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        next_prune = monotonic()
        url = f"http://127.0.0.1:{server.server_port}"
        try:
            opener = build_opener(ProxyHandler({}))
            with opener.open(url + "/health", timeout=3) as response:
                if json.load(response) != {"status": "ok"}:
                    raise ValueError("Unexpected health response.")
            print(f"Declan 2.0 is ready at {url}/", flush=True)
            if args.open:
                webbrowser.open(url + "/")
            while worker.is_alive():
                worker.join(timeout=0.5)
                if monotonic() >= next_prune:
                    try:
                        history.prune()
                    except (OSError, sqlite3.Error):
                        print("Conversation history could not be pruned.", flush=True)
                    next_prune = monotonic() + 3600
        except (URLError, TimeoutError, ValueError) as error:
            parser.exit(1, f"Declan bound {url} but its local health check failed: {error}\n")
        except KeyboardInterrupt:
            print("Declan 2.0 stopped.")
        finally:
            server.shutdown()
            worker.join()


if __name__ == "__main__":
    main()
