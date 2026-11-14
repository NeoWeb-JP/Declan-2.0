"""Local Declan 2.0 chat prototype. Run with python server.py."""
import argparse
import ipaddress
import json
import logging
import os
import re
import secrets
import sqlite3
import subprocess
from collections import OrderedDict
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from declan_ingress.http_server import BoundedHTTPServer as ThreadingHTTPServer
from declan_ingress.security import response_headers, secure_page
import ha_inventory
from pathlib import Path
from threading import Lock, Thread
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from arbitration import CaptureArbiter

import conditions
import diagnostics
import configuration
import voice_profiles
import voicepipeline
import device_status
import history
import music
import approved_media_players
import timers
import updates
import web_stt
from personality import add_sass, choose_line


SESSIONS = OrderedDict()
SESSION_LOCK = Lock()
CAPTURE_ARBITER = CaptureArbiter()
ROUTINE_LOCKS = {name: Lock() for name in ("morning", "night", "movie")}
ROUTINE_LOCKS["movie_bedroom"] = Lock()
routine_last_attempts = {}
IDLE_SECONDS = 300
ASSIST_PORT = 52737
RELEASE_VERSION = os.environ.get("DECLAN_RELEASE_VERSION", "").strip()
if not re.fullmatch(r"v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.+-]+)?", RELEASE_VERSION) or len(RELEASE_VERSION) > 40:
    RELEASE_VERSION = None
RELEASE_VERSION = updates.installed_version(RELEASE_VERSION)
SEXY_TIME_COMMANDS = {
    **{phrase: "start" for name in ("sexy time", "sixty time", "60 time", "bedroom mood", "romance mode")
       for phrase in (name, f"start {name}", f"activate {name}")},
    **{phrase: "end" for name in ("sexy time", "sixty time", "60 time", "bedroom mood", "romance mode")
       for phrase in (f"end {name}", f"stop {name}")},
}
SEXY_TIME_LOCK = Lock()
SEXY_TIME_SCRIPT = "script.declan_sexy_time_controller"
DINNER_SCRIPT = "script.declan_dinner_is_served_2"
DINNER_PHRASES = {
    "dinner is served", "it's dinner time", "time for dinner", "it's time for dinner",
    "announce dinner", "start dinner time", "dinner time",
}
GUEST_MODE_ENTITY = "input_boolean.guest_mode"
GUEST_REGISTER_ENTITY = "input_text.guests_in_charge"
GUEST_COMMANDS = {
    "who is in charge": "check",
    "who is looking after the house": "check",
    "the guests have left": "clear",
    "our guests have left": "clear",
    "clear the guests in charge": "clear",
}
UNMATCHED_REPLY = "I didn't catch what you wanted me to do. Could you say it another way?"
NAME_PATTERN = re.compile(r"my name is ([^\W\d_][\w '\u2019-]{0,39})", re.I)
CHAT_COMMANDS = {
    "what's my name": "recall_name", "what is my name": "recall_name",
    "do you remember my name": "recall_name",
    "what did i just say": "recall_message", "what did i say": "recall_message",
    "what time is it": "time", "what is the time": "time", "tell me the time": "time",
    "what's the time": "time", "what’s the time": "time",
    "hello": "greeting", "hi": "greeting", "hey": "greeting", "hello declan": "greeting",
}
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


def read_guest_mode():
    url = os.environ.get("DECLAN_HA_URL", "").strip().rstrip("/")
    token = os.environ.get("DECLAN_HA_TOKEN", "").strip()
    try:
        parsed = urlsplit(url)
        if (not token or parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            return None
        request = Request(f"{url}/api/states/{GUEST_MODE_ENTITY}", headers={"Authorization": f"Bearer {token}"})
        opener = build_opener(ProxyHandler({}), NoRedirect())
        with opener.open(request, timeout=1) as response:
            return json.loads(response.read(4096)).get("state")
    except HTTPError as error:
        error.close()
    except (OSError, ValueError, AttributeError):
        pass
    return None


def routine_action_results(steps):
    if isinstance(steps, dict):
        steps = [{"target": target, "status": status} for target, status in steps.items()]
    if not isinstance(steps, list):
        return []
    return [
        {
            **{key: step[key][:240] for key in ("target", "status", "action", "entity_id", "detail", "evidence", "observed_at")
               if isinstance(step.get(key), str)},
            **({"required": step["required"]} if type(step.get("required")) is bool else {}),
        }
        for step in steps[:200]
        if isinstance(step, dict) and isinstance(step.get("target"), str)
        and step.get("status") in ("confirmed", "already_set", "skipped", "failed", "unverified", "planned")
    ]


MOVIE_APPS = {
    "netflix": ("Netflix", "netflix"),
    "prime video": ("Prime Video", "prime video"),
    "disney plus": ("Disney+", "Disney+"),
    "disney+": ("Disney+", "Disney+"),
    "paramount plus": ("Paramount+", "Paramount+"),
    "paramount+": ("Paramount+", "Paramount+"),
}
MOVIE_ROOMS = r"lounge|living room|bedroom|master bedroom|here"


def parse_movie_request(phrase):
    shortcut = re.fullmatch(rf"(?:open|launch) (.+?) in (?:the )?({MOVIE_ROOMS})", phrase)
    if shortcut and shortcut[1] in MOVIE_APPS:
        app, room = shortcut.groups()
        return "start", room, app
    match = re.fullmatch(
        r"(?:(start|turn on|end|stop|turn off|toggle) )?(?:movie time|cinema time|cinema mode)"
        rf"(?: in (?:the )?({MOVIE_ROOMS}))?(?: and (?:open|launch) (.+))?",
        phrase,
    )
    if not match:
        return None
    verb, room, app = match.groups()
    if app:
        app_room = re.fullmatch(rf"(.+?) in (?:the )?({MOVIE_ROOMS})", app)
        if app_room and room is None:
            app, room = app_room.groups()
    direction = ("start" if verb in ("start", "turn on") else
                 "end" if verb in ("end", "stop", "turn off") else "toggle")
    return direction, room, app


def select_routine(phrase, origin):
    phrase = phrase.removeprefix("run ").removeprefix("the ")
    if phrase in GOOD_MORNING_PHRASES:
        return "morning", {}
    if phrase in GOOD_NIGHT_PHRASES:
        return "night", {}
    movie = parse_movie_request(phrase)
    if not movie:
        return None
    direction, room, app = movie
    if room in (None, "here"):
        area = None
        if origin and (connection := ha_device_connection()):
            areas = read_ha_areas(connection, origin)
            area = next(iter(areas), None)
        if area in ("lounge", "living room", "bedroom", "master bedroom"):
            room = area
        elif room == "here" or origin and not area:
            return "movie", None
    return "movie", {
        "movie_action": direction,
        "movie_room": "bedroom" if room in ("bedroom", "master bedroom") else "lounge",
        "requested_app": app,
    }


def select_routine_turn(phrase, origin):
    for join in re.finditer(r"(?:,\s*|\s+)(?:and then|and|then) (?=turn |make |set |dim |play )", phrase):
        follow_on = phrase[join.end():]
        if follow_on.startswith("play ") and parse_movie_request(phrase[:join.start()].removeprefix("run ")):
            continue
        if routine := select_routine(phrase[:join.start()], origin):
            return routine, follow_on
    routine = select_routine(phrase, origin)
    return (routine, None) if routine else None


def execute_routine(selection, action_results):
    period, options = selection
    if options is None:
        return "Which room do you mean for Movie Time?", "unresolved", None
    options = options.copy()
    requested_app = options.pop("requested_app", None)
    app = MOVIE_APPS.get(requested_app)
    if requested_app and (not app or options.get("movie_action") != "start"):
        return "Please name a supported app with an explicit start Movie Time command.", "unresolved", None
    return run_routine(period, movie_app=app, action_results=action_results, **options)


def chained_outcome(routine, lighting):
    if routine == "reported_success" and lighting == "confirmed":
        return "reported_success"
    if routine in {"reported_success", "partial"} or lighting in {"confirmed", "partial"}:
        return "partial"
    if "unverified" in (routine, lighting):
        return "unverified"
    return routine if routine == lighting else "failed"


def search_media(phrase):
    match = re.fullmatch(
        r"(?:where can i (?:watch|stream|find)|(?:search|look) for|find (?:the )?(?:movie|film|show)|"
        r"start (?:movie time|cinema time|cinema mode) and play(?: the (?:movie|film|show))?) (.+)",
        phrase,
    )
    if not match:
        return None
    title = match[1].strip()
    if len(title) > 200 or re.search(r"\b(?:and|then)\s+(?:turn|switch|dim|brighten|set|start|stop|unlock|lock|open|play)\b", title):
        return "Please ask for the film or show separately from any device commands.", "unresolved"
    agent = configuration.get("DECLAN_MEDIA_SEARCH_AGENT", "").strip()
    if agent and not re.fullmatch(r"conversation\.[a-z0-9_]+", agent):
        return "The Declan Local media search agent isn't configured.", "not_configured"
    connection = ha_device_connection()
    if connection is None:
        return "The Home Assistant connection isn't configured.", "not_configured"
    url, headers, opener = connection
    if not re.fullmatch(r"conversation\.(?:declan_local|jarvis_local)(?:_[a-z0-9]+)*", agent):
        template = (
            "{% set local = integration_entities('declan_local') + integration_entities('jarvis_local') %}"
            "{{ states.conversation | rejectattr('state', 'eq', 'unavailable') "
            "| map(attribute='entity_id') | select('in', local) | list | to_json }}"
        )
        request = Request(f"{url}/api/template", headers=headers,
                          data=json.dumps({"template": template}).encode())
        try:
            with opener.open(request, timeout=1.5) as response:
                entities = json.loads(response.read(65536))
            if not isinstance(entities, list):
                raise ValueError("Expected a list of conversation entities")
        except (OSError, ValueError) as error:
            if isinstance(error, HTTPError):
                error.close()
            return "I couldn't check Home Assistant for the Declan Local media search agent.", "unavailable"
        candidates = {
            entity for entity in entities if isinstance(entity, str)
            and re.fullmatch(r"conversation\.[a-z0-9_]+", entity)
        }
        if agent and agent not in candidates:
            return "The configured media search agent isn't available in Declan Local.", "not_configured"
        if not agent:
            if not candidates:
                return "I couldn't find an active Declan Local conversation agent in Home Assistant.", "not_configured"
            if len(candidates) > 1:
                return "I found multiple Declan Local agents. Set DECLAN_MEDIA_SEARCH_AGENT to the one you use for media search.", "not_configured"
            agent = candidates.pop()
    try:
        request = Request(f"{url}/api/services/conversation/process?return_response",
                          data=json.dumps({"agent_id": agent, "text": f"where can i watch {title}"}).encode(),
                          headers=headers)
        with opener.open(request, timeout=18) as response:
            payload = json.loads(response.read(1024 * 1024))["service_response"]["response"]
        reply = payload["speech"]["plain"]["speech"]
        if isinstance(reply, str) and reply.strip() and payload.get("response_type") != "error":
            return reply.strip(), "search_result"
    except HTTPError as error:
        error.close()
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return "I couldn't get a title search result from Declan Local.", "unverified"


def launch_movie_app(connection, remote, app):
    label, command = app
    url, headers, opener = connection
    try:
        with opener.open(Request(f"{url}/api/states/{remote}", headers=headers), timeout=1.5) as response:
            state = json.loads(response.read(65536))["state"]
        if state in ("unknown", "unavailable"):
            return "skipped", f"The remote is unavailable. I didn't send the {label} command."
        request = Request(f"{url}/api/services/remote/send_command", headers=headers,
                          data=json.dumps({"entity_id": remote, "command": ["KEY_HOME", f"app:{command}"],
                                           "delay_secs": 2}).encode())
        with opener.open(request, timeout=6):
            pass
    except HTTPError as error:
        error.close()
        return "failed", f"Home Assistant rejected the {label} launch request."
    except (OSError, ValueError, KeyError, TypeError):
        return "unverified", f"I couldn't confirm whether Home Assistant accepted the {label} launch request."
    return "sent", f"Home Assistant accepted the command to open {label}."


def discover_movie_entities(connection, room, *, script, remote, needs_remote):
    inventory, error = read_ha_inventory(connection)
    if error:
        return script, remote, "I couldn't read the Home Assistant entity list."
    room_names = {"lounge": ("lounge", "living room"), "bedroom": ("bedroom", "master bedroom")}
    areas = read_ha_areas(connection) if needs_remote and not remote else {}
    area_members = set().union(*(areas.get(name, set()) for name in room_names[room]))
    candidates = {"script": set(), "remote": set()}
    for row in inventory:
        if not isinstance(row, dict):
            continue
        entity = row.get("entity_id")
        if not isinstance(entity, str) or not re.fullmatch(r"(?:script|remote)\.[a-z0-9_]+", entity):
            continue
        domain, object_id = entity.split(".", 1)
        attrs = row.get("attributes") or {}
        names = [" ".join(re.findall(r"[a-z0-9]+", name.casefold()))
                 for name in (object_id, attrs.get("friendly_name", ""))
                 if isinstance(name, str)]
        named_rooms = {key for key, labels in room_names.items()
                       if any(re.search(rf"\b{label}\b", name) for label in labels for name in names)}
        if named_rooms - {room}:
            continue
        if domain == "script" and not script:
            if not named_rooms and room != "lounge":
                continue
            for name in names:
                for label in sorted(room_names[room], key=len, reverse=True):
                    name = re.sub(rf"\b{label}\b", "", name)
                if re.fullmatch(r"(?:declan )?movie time shared local routine(?: \d+)?", " ".join(name.split())):
                    candidates["script"].add(entity)
        elif domain == "remote" and needs_remote and not remote:
            assigned = any(entity in members for members in areas.values())
            in_room = entity in area_members if assigned else room in named_rooms
            if in_room and any("projector" in name.split() for name in names):
                candidates["remote"].add(entity)
    for domain, configured, label in (("script", script, "Movie Time script"), ("remote", remote, "projector remote")):
        if configured or (domain == "remote" and not needs_remote):
            continue
        matches = candidates[domain]
        if len(matches) != 1:
            setting = ("DECLAN_BEDROOM_MOVIE" if room == "bedroom" else "DECLAN_MOVIE") + "_" + domain.upper()
            detail = "found more than one" if matches else "couldn't find a"
            return script, remote, f"I {detail} {label} for the {room}. Set {setting} to the exact entity ID."
        if domain == "script":
            script = next(iter(matches))
        else:
            remote = next(iter(matches))
    return script, remote, None


def verify_legacy_lounge_start(connection, script):
    inventory, error = read_ha_inventory(connection)
    if error:
        return "Home Assistant didn't return the lounge device states."
    entities = {row.get("entity_id"): row for row in inventory if isinstance(row, dict)}
    if entities.get(script, {}).get("state") != "off":
        return "Home Assistant hasn't confirmed the Movie Time script is off."
    if entities.get("switch.projector_power_socket", {}).get("state") != "on":
        return "The projector power socket hasn't reported that it's on."
    return None


@diagnostics.timed("ha_routine")
def run_routine(period, *, action_results=None, movie_action=None, movie_room="lounge", movie_app=None):
    """Call the configured Home Assistant routine once and read its result."""
    salutation = "Movie Time." if movie_action else f"Good {period}."
    lock = ROUTINE_LOCKS["movie_bedroom" if movie_action and movie_room == "bedroom" else period]
    connection = ha_device_connection()
    if connection is None:
        return f"{salutation} The Home Assistant connection isn't configured.", "not_configured", None
    url, headers, opener = connection
    movie_prefix = "DECLAN_BEDROOM_MOVIE" if movie_room == "bedroom" else "DECLAN_MOVIE"
    setting = f"{movie_prefix}_SCRIPT" if movie_action else f"DECLAN_GOOD_{period.upper()}_SCRIPT"
    default_script = {"morning": GOOD_MORNING_SCRIPT, "night": GOOD_NIGHT_SCRIPT}.get(period, "")
    script = configuration.get(setting, default_script).strip()
    remote = configuration.get(f"{movie_prefix}_REMOTE", "").strip() if movie_app else ""
    if movie_action and (not script or (movie_app and not remote)):
        script, remote, error = discover_movie_entities(
            connection, movie_room, script=script, remote=remote, needs_remote=bool(movie_app),
        )
        if error:
            return f"{salutation} {error}", "not_configured", None
    if movie_app and not re.fullmatch(r"remote\.[a-z0-9_]+", remote):
        return f"I don't have a compatible app remote configured for the {movie_room}.", "not_configured", None
    if not re.fullmatch(r"script\.[a-z0-9_]+", script):
        return f"{salutation} The routine script isn't configured.", "not_configured", None
    if not lock.acquire(blocking=False):
        return f"The {period} routine request is already in progress.", "busy", None
    try:
        attempt_key = (period, movie_room, movie_action) if movie_action else period
        last_attempt = routine_last_attempts.get(attempt_key)
        if last_attempt is not None and monotonic() - last_attempt < 30:
            return f"I already sent a {period} request. I haven't sent another.", "duplicate", None
        routine_last_attempts[attempt_key] = monotonic()
        service = script.split(".", 1)[1]
        request_id = "declan-" + secrets.token_hex(16)
        parameters = {"request_id": request_id, "routine_id": script}
        if movie_action:
            parameters["requested_action"] = movie_action
        request = Request(
            f"{url}/api/services/script/{service}?return_response",
            data=json.dumps(parameters).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with opener.open(request, timeout={"morning": 8, "night": 20, "movie": 55}[period]) as response:
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
        if movie_action and isinstance(result, dict) and set(result) == {script}:
            result = result[script]
        if movie_action or (isinstance(result, dict) and "schema_version" in result):
            reply, outcome, detail = format_routine_result(result, request_id, script, period, movie_action, action_results)
            if movie_app:
                legacy_result = result is None or (isinstance(result, dict)
                    and result.get("schema_version") in (None, 1)
                    and result.get("request_id") in (None, "", request_id)
                    and result.get("routine_id") in (None, "", script)
                    and result.get("outcome") in (None, "success")
                    and result.get("status") in (None, "success")
                    and (not result.get("request_id") or not result.get("routine_id")))
                legacy_start = legacy_result and movie_room == "lounge" and movie_action == "start"
                if outcome == "reported_success" or legacy_start:
                    sleep(7)
                readiness_error = verify_legacy_lounge_start(connection, script) if legacy_start else None
                legacy_ready = legacy_start and readiness_error is None
                if outcome == "reported_success" or legacy_ready:
                    if legacy_ready:
                        detail = "Home Assistant shows Movie Time has finished and the lounge projector socket is on."
                        reply = add_sass("Starting Movie Time.", "movie_start", read_guest_mode())
                        outcome = "partial"
                    status, note = launch_movie_app(connection, remote, movie_app)
                else:
                    status, note = "skipped", readiness_error or detail or "Movie Time wasn't confirmed."
                    if readiness_error:
                        reply, detail = f"{salutation} {readiness_error}", readiness_error
                if action_results is not None:
                    action_results.append({
                        "target": movie_app[0], "action": "open_app", "status": status, "entity_id": remote,
                        "detail": f"{note} Remote: {remote}. Command: app:{movie_app[1]}.",
                    })
            return reply, outcome, detail
        status = result.get("status") if isinstance(result, dict) else None
        steps = result.get("steps") if isinstance(result, dict) else None
        if action_results is not None:
            action_results.extend(routine_action_results(steps))
        guest_mode = result.get("guest_mode") if isinstance(result, dict) else None
        if status == "success" and isinstance(result, dict) and "guest_mode" not in result:
            guest_mode = read_guest_mode()
        greeting = add_sass(salutation, f"good_{period}", guest_mode) if status == "success" else salutation
        bedtime = result.get("bedtime") if isinstance(result, dict) else None
        if period == "night" and guest_mode == "off" and isinstance(bedtime, dict):
            battery = bedtime.get("battery_percent")
            temperature = bedtime.get("indoor_temperature")
            if type(battery) is int and 0 <= battery <= 50:
                reminder = f"The Peugeot is at {battery}% and isn't plugged in."
                if status == "success":
                    reminder = add_sass(reminder, "bedtime_ev", guest_mode)
                greeting += f" {reminder}"
            if type(temperature) in (int, float) and -40 <= temperature <= 16:
                greeting += f" It's {temperature:g} degrees indoors and the heating isn't running."
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
            detail = " ".join(details)
            return f"{greeting} {detail}".strip(), "unverified", detail
        if period == "night" and status in (None, "unverified", "success"):
            detail = result.get("routine_status") if isinstance(result, dict) else None
            verified = status == "success"
            fallback = ("Home Assistant reports the routine completed." if verified
                        else "Home Assistant did not confirm the bedtime routine completed.")
            detail = detail if isinstance(detail, str) and detail.strip() else fallback
            return (greeting if verified else f"{greeting} {detail}"), (
                "reported_success" if verified else "unverified"), detail
        if status == "success":
            return greeting, "reported_success", "Home Assistant reports the routine completed."
        if status == "partial":
            return f"{salutation} Part of the routine failed. Check its Home Assistant trace.", "partial", None
        if status == "failed":
            return f"{salutation} Home Assistant reported a failure in the routine.", "failed", None
        if status == "busy":
            return f"{salutation} Home Assistant reports the routine is already running.", "busy", None
        return f"{salutation} Home Assistant answered, but I couldn't verify the device changes.", "unverified", None
    finally:
        lock.release()


def format_routine_result(result, request_id, routine_id, period, movie_action, action_results):
    salutation = "Movie Time." if movie_action else f"Good {period}."
    if (not isinstance(result, dict) or result.get("schema_version") != 1
            or result.get("request_id") != request_id or result.get("routine_id") != routine_id):
        if movie_action:
            detail = "Home Assistant didn't return a Movie Time result that matched this request."
            return f"{salutation} {detail}", "unverified", detail
        return f"{salutation} I couldn't verify the result of this run.", "unverified", None
    outcome = result.get("outcome")
    resolved = result.get("resolved_action")
    if movie_action and outcome in ("success", "partial"):
        expected = ("start", "end") if movie_action == "toggle" else (movie_action,)
        if resolved not in expected:
            return "Movie Time. I couldn't verify that the result matched the requested direction.", "unverified", None
    raw_steps = result.get("steps")
    steps = routine_action_results(raw_steps)
    if action_results is not None:
        action_results.extend(steps)
    completed = {"confirmed", "already_set"}
    required = [step for step in steps if step.get("required", True)]
    confirmed = any(step["status"] in completed for step in required)
    if outcome == "success" and (not required or len(steps) != len(raw_steps)
                                 or any(step["status"] not in completed for step in required)):
        outcome = "partial" if confirmed else "unknown"
    elif outcome == "partial" and not confirmed:
        outcome = "unknown"
    elif outcome == "failed" and confirmed:
        outcome = "partial"
    if outcome == "success":
        guest_mode = result.get("guest_mode")
        if movie_action:
            salutation = "Starting Movie Time." if resolved == "start" else "Ending Movie Time."
        category = f"movie_{resolved}" if movie_action else f"good_{period}"
        reply = add_sass(salutation, category, guest_mode)
        bedtime = result.get("bedtime")
        if period == "night" and guest_mode == "off" and isinstance(bedtime, dict):
            battery = bedtime.get("battery_percent")
            temperature = bedtime.get("indoor_temperature")
            if type(battery) is int and 0 <= battery <= 50:
                reminder = add_sass(f"The Peugeot is at {battery}% and isn't plugged in.", "bedtime_ev", guest_mode)
                reply += f" {reminder}"
            if type(temperature) in (int, float) and -40 <= temperature <= 16:
                reply += f" It's {temperature:g} degrees indoors and the heating isn't running."
        detail = ("Home Assistant reports all lights are off." if period == "night"
                  else "Home Assistant confirmed the required steps.")
        return reply, "reported_success", detail
    if outcome == "busy":
        return f"{salutation} The routine is already in progress.", "busy", None
    verified = [step["target"].replace("_", " ") for step in required if step["status"] in completed]
    failed = [step["target"].replace("_", " ") for step in required if step["status"] == "failed"]
    incomplete = [step["target"].replace("_", " ") for step in required
                  if step["status"] not in completed and step["status"] != "failed"]
    details = []
    if verified:
        details.append("Home Assistant confirmed " + ", ".join(verified[:8]) + ".")
    if failed:
        details.append("These steps failed: " + ", ".join(failed[:8]) + ".")
    if incomplete:
        details.append("I couldn't confirm " + ", ".join(incomplete[:8]) + ".")
    detail = " ".join(details) or ("Home Assistant reported a failure." if outcome == "failed"
                                   else "I couldn't confirm the routine completed.")
    reply = f"{salutation} {detail}"
    if movie_action and outcome == "partial" and resolved in ("start", "end"):
        intro = "Starting Movie Time." if resolved == "start" else "Ending Movie Time."
        reply = add_sass(intro, f"movie_{resolved}", result.get("guest_mode"))
    return reply, outcome if outcome in ("partial", "failed") else "unverified", detail


def parse_light_command(phrase):
    separator = r"\s+(?:and then|as well as|and|then)\s+(?=(?:turn|make)\s)"
    if re.match(r"turn (?!on\b|off\b)", phrase):
        separator += r"|(?:(?<= on)|(?<= off))\s+(?:and then|as well as|and|then)\s+"
    if phrase.startswith("make "):
        separator += r"|(?:(?<= darker)|(?<= lighter)|(?<= brighter)|(?<= very bright))\s+(?:and then|as well as|and|then)\s+"
    clauses = re.split(separator, phrase)
    targets = []
    for index, clause in enumerate(clauses):
        relative_prefix = r"(?:make )?" if index and phrase.startswith("make ") else "make "
        relative = re.fullmatch(relative_prefix + r"(?:the )?(.+?) (darker|lighter|brighter|very bright)", clause)
        if relative:
            targets.append((relative[1], "brighter" if relative[2] == "lighter" else relative[2]))
            continue
        exception = re.fullmatch(r"turn (?:everything|all lights) off except (?:for )?(?:the )?(.+)", clause)
        if exception:
            targets.append(("everything except " + exception[1], "off"))
            continue
        command = (
            re.fullmatch(r"turn (?P<state>on|off)(?:\s*[,;:]\s*|\s+)(?:the )?(?P<name>.+)", clause)
            or re.fullmatch(r"(?:turn )?(?:the )?(?P<name>.+) (?P<state>on|off)", clause)
        )
        if command is None:
            return None
        targets.append(command.group("name", "state"))
    name, direction = targets[0]
    for target, state in targets[1:]:
        verb = "make" if state in ("darker", "brighter", "very bright") else "turn"
        name += f" and {verb} {state} {target}"
    return name, direction


@diagnostics.timed("lighting")
def handle_light_request(phrase, *, action_results=None, last_lights=(), origin_device=None):
    if phrase in {"what lights are on", "which lights are on", "what lights are still on", "which lights are still on"}:
        return set_lights("", None)
    preview = re.match(r"^(?:preview|dry[ -]run)\b[ ,:]*", phrase)
    if preview:
        phrase = phrase[preview.end():]
    room_adjustment = re.fullmatch(r"make it (darker|lighter|brighter|very bright) in (.+)", phrase)
    turn_adjustment = re.fullmatch(r"turn (down|up) ((?:the )?(?:all )?lights(?: in .+)?)", phrase)
    if room_adjustment:
        phrase = f"make the lights in {room_adjustment[2]} {room_adjustment[1]}"
    elif turn_adjustment:
        direction = "darker" if turn_adjustment[1] == "down" else "brighter"
        phrase = f"make {turn_adjustment[2]} {direction}"
    if phrase.endswith(" in here"):
        contextual = phrase.removesuffix(" in here")
        if re.fullmatch(r"make it (?:darker|lighter|brighter|very bright)", contextual):
            contextual = contextual.replace("make it ", "make the lights ", 1)
        command = parse_light_command(contextual)
        if command is None or re.search(r"\b(?:actually|i mean|turn|make|except)\b", command[0]):
            return "Please give me one lighting action for this room.", "unresolved"
        if origin_device is None:
            return "Which room do you mean? I can't identify a room for this request.", "unresolved"
        if command[0] == "some lights" and command[1] != "on":
            return "Please name the lights you want to change in this room.", "unresolved"
        return set_lights(*command, preview=bool(preview), action_results=action_results,
                          origin_device=origin_device)
    follow_up = (
        re.fullmatch(r"turn (it|them) (on|off)", phrase)
        or re.fullmatch(r"(?:turn )?(on|off) (it|them)", phrase)
        or re.fullmatch(r"make (it|them) (darker|lighter|brighter|very bright)", phrase)
    )
    if follow_up:
        pronoun, direction = follow_up.groups()
        if direction in ("it", "them"):
            pronoun, direction = direction, pronoun
        if not last_lights or (pronoun == "it") != (len(last_lights) == 1):
            return "Which light or room do you mean?", "unresolved"
        return set_lights(" and ".join(last_lights), "brighter" if direction == "lighter" else direction,
                          preview=bool(preview), require_all=True, action_results=action_results)
    parts = re.split(r"[ ,;]+(?:actually|no[ ,]+i mean|i mean|no(?=,))\b[ ,:;]*", phrase)
    corrected = len(parts) > 1
    if corrected and re.search(r"(?:^|\s)(?:and|then|as well as|in the|except(?: the)?)$", parts[-1]):
        return "Please finish the corrected light command.", "unresolved"
    brightness = None
    relative_step = 10
    dimming = re.fullmatch(r"(?:set|dim) (?:the )?(.+?) to\s+([+-]?\d+)\s*(?:percent|per cent|%)", parts[-1])
    adjustment = re.fullmatch(r"(dim|brighten) (?:the )?(.+?) by\s+([+-]?\d+)\s*(?:percent|per cent|%)", parts[-1])
    if dimming:
        brightness = int(dimming[2])
        if not 0 <= brightness <= 100:
            return "Please choose a brightness from 0 to 100 percent.", "unresolved"
        if re.search(r"\bturn (?:on|off)\b", dimming[1]):
            return "Please give the brightness and on/off changes as separate commands.", "unresolved"
        command = dimming[1], "on" if brightness else "off"
    elif adjustment:
        relative_step = int(adjustment[3])
        if not 1 <= relative_step <= 100:
            return "Please choose a brightness change from 1 to 100 percent.", "unresolved"
        command = adjustment[2], "darker" if adjustment[1] == "dim" else "brighter"
    else:
        command = parse_light_command(parts[-1])
    if corrected and command is None:
        previous = parse_light_command(parts[0])
        replacement = parts[-1].removeprefix("the ").strip()
        if (previous and replacement and not previous[0].startswith("everything except ")
                and not re.search(r"\b(?:turn (?:on|off)|make (?:darker|brighter|very bright))\b", previous[0])
                and not re.match(r"^(?:turn|switch|make|on|off|the)\b", replacement)):
            command = replacement, previous[1]
    if command is None:
        if corrected:
            return "Please say the corrected light command in full.", "unresolved"
        if preview:
            return "Please give me a lighting command to preview.", "unresolved"
        return None
    return set_lights(*command, brightness=brightness or None, preview=bool(preview),
                      require_all=corrected, action_results=action_results, relative_step=relative_step)


def ha_device_connection():
    url = os.environ.get("DECLAN_HA_URL", "").strip().rstrip("/")
    token = os.environ.get("DECLAN_HA_TOKEN", "").strip()
    try:
        parsed = urlsplit(url)
        configured = (token and parsed.scheme in {"http", "https"} and parsed.hostname
                      and not any((parsed.username, parsed.password, parsed.query, parsed.fragment)))
    except ValueError:
        configured = False
    if not configured:
        return None

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    opener = build_opener(ProxyHandler({}), NoRedirect())
    return url, headers, opener


@diagnostics.timed("bedroom_routine")
def run_sexy_time(operation, connection):
    if connection is None:
        return "The Home Assistant connection isn't configured.", "not_configured", None
    if not SEXY_TIME_LOCK.acquire(blocking=False):
        return "I'm still handling the previous Sexy Time request.", "busy", None
    try:
        inventory, inventory_error = read_music_inventory(connection)
        if inventory_error:
            return "I couldn't discover the bedroom music player.", inventory_error, None
        destinations, _ = music.music_players(inventory)
        player = destinations.get("bedroom")
        if not player:
            return "I couldn't identify one available bedroom satellite speaker. Check its Home Assistant device and area.", "unresolved", None
        url, headers, opener = connection
        request = Request(
            f"{url}/api/services/script/{SEXY_TIME_SCRIPT.split('.', 1)[1]}?return_response", headers=headers,
            data=json.dumps({"operation": operation, "music_player": player}).encode(), method="POST",
        )
        try:
            with opener.open(request, timeout=8) as response:
                payload = json.loads(response.read(65536))
        except HTTPError as error:
            error.close()
            return "I couldn't confirm the bedroom routine completed. Check its Home Assistant trace.", "unverified", None
        except (OSError, ValueError):
            return "I couldn't confirm the bedroom routine completed. Check its Home Assistant trace.", "unverified", None

        result = payload.get("service_response") if isinstance(payload, dict) else None
        if isinstance(result, dict) and set(result) == {SEXY_TIME_SCRIPT}:
            result = result[SEXY_TIME_SCRIPT]
        if not isinstance(result, dict) or result.get("operation") != operation:
            return "I couldn't verify the bedroom routine's result.", "unverified", None

        lighting_ok = result.get("lighting_ok") is True
        if operation == "end":
            _, music_outcome = music.control(
                ("media_stop", "bedroom"), connection, lambda _: (inventory, None),
            )
            music_ok = music_outcome == "confirmed"
            if lighting_ok:
                detail = None if music_ok else "Bedroom lights restored. Bedroom music stop could not be verified."
                return choose_line("sexy_time_end", read_guest_mode()), "confirmed" if music_ok else "partial", detail
            playback = "The music has stopped." if music_ok else "I couldn't verify that the bedroom music stopped."
            return f"I couldn't verify the bedroom lights. {playback}", "partial" if music_ok else "unverified", None

        if not lighting_ok:
            return "I couldn't verify the bedroom lights, so I held off on the playlist.", "unverified", None
        volume_ok = True
        try:
            music.request(connection, "/api/services/media_player/volume_set",
                          {"entity_id": player, "volume_level": 0.2})
        except (OSError, ValueError):
            volume_ok = False
        reply, outcome = music.play(("bedroom", "sexy time music", "spotify"), connection,
                                    lambda _: (inventory, None))
        spoken = choose_line("sexy_time_start", read_guest_mode())
        if outcome == "confirmed" and volume_ok:
            return spoken, "confirmed", None
        volume_detail = "" if volume_ok else " Bedroom music volume could not be set."
        return spoken, "partial", f"Bedroom lights set. {reply}{volume_detail}"
    finally:
        SEXY_TIME_LOCK.release()


@diagnostics.timed("dinner_dispatch")
def start_dinner(connection):
    if connection is None:
        return "The Home Assistant connection isn't configured.", "not_configured"
    url, headers, opener = connection
    announcement = choose_line("dinner_announcement", read_guest_mode())
    request = Request(
        f"{url}/api/services/script/turn_on", headers=headers,
        data=json.dumps({
            "entity_id": DINNER_SCRIPT, "variables": {"dinner_message": announcement},
        }).encode(), method="POST",
    )
    try:
        with opener.open(request, timeout=2):
            pass
    except HTTPError as error:
        error.close()
        if 400 <= error.code < 500:
            return "Home Assistant rejected the dinner announcement request.", "unavailable"
        return "I couldn't confirm that Home Assistant accepted the dinner announcement request.", "unverified"
    except OSError:
        return "I couldn't confirm that Home Assistant accepted the dinner announcement request.", "unverified"
    return announcement, "requested"


def guest_assignment(operation, connection):
    if connection is None:
        return "I couldn't reach Home Assistant to check Guest Mode or the guest register.", "unavailable"
    url, headers, opener = connection

    def request(path, data=None):
        body = json.dumps(data).encode() if data is not None else None
        try:
            with opener.open(Request(url + path, headers=headers, data=body), timeout=1.5) as response:
                return json.loads(response.read(8192))
        except HTTPError as error:
            error.close()
        except (OSError, ValueError):
            pass
        return None

    def read_state(entity):
        payload = request(f"/api/states/{entity}")
        state = payload.get("state") if isinstance(payload, dict) else None
        if not isinstance(state, str) or state.strip().casefold() in {"unknown", "unavailable"}:
            return None
        return state.strip()

    if operation == "clear":
        request("/api/services/input_text/set_value", {"entity_id": GUEST_REGISTER_ENTITY, "value": ""})
        names = read_state(GUEST_REGISTER_ENTITY)
        # Keep Guest Mode in place until the register is verified empty.
        if names != "":
            return "I couldn't verify that the guest register was cleared, so I left Guest Mode alone.", "unverified"
        request("/api/services/input_boolean/turn_off", {"entity_id": GUEST_MODE_ENTITY})
        if read_state(GUEST_MODE_ENTITY) != "off":
            return "I cleared the guest register, but couldn't verify that Guest Mode is off.", "partial"
        return add_sass("I cleared the guest register and turned off Guest Mode.", "guest_cleared", "off"), "confirmed"

    mode = read_state(GUEST_MODE_ENTITY)
    names = read_state(GUEST_REGISTER_ENTITY)
    if mode not in {"on", "off"} or names is None:
        return "I couldn't read Guest Mode or the guest register.", "unavailable"
    if mode == "on":
        if names:
            return f"Currently in charge: {names}. Guest Mode is on.", "confirmed"
        return "Guest Mode is on, but nobody is listed in the guest register.", "confirmed"
    if names:
        return f"Guest Mode is off, but the guest register still lists {names}.", "confirmed"
    return add_sass("Guest Mode is off. The house is back in your hands.", "guest_inactive", mode), "confirmed"


@diagnostics.timed("speech_generation")
def render_web_voice(message):
    connection = ha_device_connection()
    engine = configuration.get("DECLAN_WEB_TTS_ENTITY", "").strip()
    if connection is None or (engine and not re.fullmatch(r"tts\.[a-z0-9_]+", engine)):
        return None
    url, headers, opener = connection
    try:
        if not engine:
            template = (
                "{% set providers = integration_entities('elevenlabs') + integration_entities('elevenlabs_custom_tts') %}"
                "{% set result = namespace(engines=[]) %}"
                "{% for entity in states.tts if entity.state != 'unavailable' "
                "and (entity.entity_id in providers or 'elevenlabs' in entity.entity_id or 'elevenlabs' in entity.name | lower) %}"
                "{% set result.engines = result.engines + [[entity.entity_id, entity.name]] %}"
                "{% endfor %}{{ result.engines | to_json }}"
            )
            request = Request(f"{url}/api/template", headers=headers,
                              data=json.dumps({"template": template}).encode())
            with opener.open(request, timeout=2) as response:
                rows = json.loads(response.read(16384))
            candidates = {entity: name for entity, name in rows
                          if isinstance(entity, str) and re.fullmatch(r"tts\.[a-z0-9_]+", entity)
                          and isinstance(name, str)}
            named = [entity for entity, name in candidates.items() if "declan" in (entity + " " + name).casefold()]
            matches = named or list(candidates)
            if len(matches) != 1:
                return None
            engine = matches[0]
        request = Request(f"{url}/api/tts_get_url", headers=headers, data=json.dumps({
            "engine_id": engine, "message": message, "cache": False,
            "options": {"preferred_format": "mp3"},
        }).encode())
        with opener.open(request, timeout=10) as response:
            path = json.loads(response.read(8192))["path"]
        if not isinstance(path, str) or not re.fullmatch(r"/api/tts_proxy/[\w.-]+\.mp3", path, re.ASCII):
            return None
        limit = 8 * 1024 * 1024
        with opener.open(Request(url + path, headers=headers), timeout=10) as response:
            audio = response.read(limit + 1)
        return audio if 0 < len(audio) <= limit else None
    except HTTPError as error:
        error.close()
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def read_ha_inventory(connection):
    return ha_inventory.read(connection)


def read_music_inventory(connection):
    return ha_inventory.read(connection, music=True)


def stop_origin_output(connection, satellite, device):
    if connection is None or not (satellite or device):
        return "", "unresolved", "Stop needs an identifiable Assist satellite or device."
    inventory, error = read_music_inventory(connection)
    if error:
        return "", error, "Could not discover the originating satellite's outputs."
    origin = next((row for row in inventory if row.get("entity_id") == satellite), None)
    origin_device = (origin.get("declan_device") if origin else None) or device
    if not origin and device:
        satellites = [row for row in inventory if str(row.get("entity_id", "")).startswith("assist_satellite.")
                      and row.get("declan_device") == device]
        origin = satellites[0] if len(satellites) == 1 else None
        satellite = origin.get("entity_id") if origin else None
    direct = [row for row in inventory if str(row.get("entity_id", "")).startswith("media_player.")
              and origin_device and row.get("declan_device") == origin_device
              and row.get("declan_music_assistant") is False
              and row.get("state") not in (None, "unknown", "unavailable")]
    if len(direct) > 1:
        return "", "unresolved", "More than one playback output belongs to the originating device."
    if len(direct) == 1:
        target = direct[0]["entity_id"]
        members = (direct[0].get("attributes") or {}).get("group_members") or []
        if len(members) > 1:
            return "", "unresolved", "The device output is grouped; Stop left the shared group alone."
        try:
            music.request(connection, "/api/services/media_player/media_stop", {"entity_id": target}, timeout=2)
            if music.wait_for(connection, target, lambda row: row.get("state") in music.STOPPED):
                if satellite:
                    timers.stop_due(satellite)
                return "", "confirmed", f"Stopped {target}."
        except HTTPError as error:
            error.close()
        except (OSError, ValueError, sqlite3.Error):
            pass
        return "", "unverified", f"Could not verify Stop on {target}."
    area = origin.get("declan_area") if origin else None
    if not isinstance(area, str) or not area.strip():
        return "", "unresolved", "No playback output or area could be resolved for the satellite."
    reply, outcome = music.control(
        ("media_stop", music.room_key(area)), connection,
        lambda _: (inventory, None),
    )
    if outcome == "confirmed" and satellite:
        try:
            timers.stop_due(satellite)
        except (OSError, sqlite3.Error):
            return "", "partial", "Playback stopped, but the local timer alarm could not be acknowledged."
    return "", outcome, reply


def read_ha_areas(connection, origin=None):
    url, headers, opener = connection
    template = (
        "{% set result = namespace(areas=[]) %}"
        "{% for id in areas() %}"
        "{% set result.areas = result.areas + [[area_name(id), area_entities(id)]] %}"
        "{% endfor %}{{ result.areas | to_json }}"
    )
    if origin is not None:
        template = (
            "{% set room = area_id(" + json.dumps(origin) + ") %}"
            "{{ ([[area_name(room), area_entities(room)]] if room else []) | to_json }}"
        )
    request = Request(f"{url}/api/template", headers=headers,
                      data=json.dumps({"template": template}).encode(), method="POST")
    try:
        with opener.open(request, timeout=1.5) as response:
            rows = json.loads(response.read(1024 * 1024))
        if not isinstance(rows, list):
            return {}
        areas = {}
        for label, entities in rows:
            if not isinstance(label, str) or not isinstance(entities, list):
                return {}
            areas.setdefault(" ".join(label.casefold().split()), set()).update(entities)
        if "master bedroom" in areas:
            areas.setdefault("bedroom", areas["master bedroom"])
        if "study" in areas:
            areas.setdefault("office", areas["study"])
        if "living room" in areas:
            areas.setdefault("lounge", areas["living room"])
        elif "lounge" in areas:
            areas.setdefault("living room", areas["lounge"])
        return areas
    except HTTPError as error:
        error.close()
    except (OSError, ValueError, TypeError, AttributeError, KeyError):
        pass
    return {}


def set_lights(name, desired_state, *, brightness=None, preview=False, require_all=False, relative_step=10,
               action_results=None, origin_device=None):
    """Resolve Home Assistant lights before dispatch and verify their reported states."""
    connection = ha_device_connection()
    if connection is None:
        return "The Home Assistant connection isn't configured.", "not_configured"
    url, headers, opener = connection
    inventory, error = read_ha_inventory(connection)
    if error:
        return "I couldn't read the lights from Home Assistant.", error

    guest_mode = next(
        (item.get("state") for item in inventory
         if isinstance(item, dict) and item.get("entity_id") == GUEST_MODE_ENTITY),
        None,
    )

    lights = {}
    names = {}
    light_groups = set()
    dimmable = set()
    levels = {}
    for item in inventory:
        entity_id = item.get("entity_id", "") if isinstance(item, dict) else ""
        if not isinstance(entity_id, str) or not re.fullmatch(r"light\.[a-z0-9_]+", entity_id):
            continue
        attributes = item.get("attributes")
        if isinstance(attributes, dict):
            modes = attributes.get("supported_color_modes")
            level = attributes.get("brightness")
            levels[entity_id] = level
            if (isinstance(level, (int, float))
                    or isinstance(modes, list) and any(mode not in ("onoff", "unknown") for mode in modes)):
                dimmable.add(entity_id)
        if isinstance(attributes, dict) and isinstance(attributes.get("entity_id"), (list, tuple, str)):
            light_groups.add(entity_id)
        friendly = attributes.get("friendly_name") if isinstance(attributes, dict) else None
        id_name = entity_id.removeprefix("light.").replace("_", " ")
        label = friendly.strip() if isinstance(friendly, str) and friendly.strip() else id_name
        lights[entity_id] = (label, item.get("state"))
        for candidate in (entity_id, id_name, " ".join(label.casefold().split())):
            names.setdefault(candidate, set()).add(entity_id)

    if desired_state is None:
        individual_lights = [light for entity, light in lights.items() if entity not in light_groups]
        if not individual_lights:
            return "Home Assistant didn't report any individual lights to check.", "unavailable"
        on = sorted(label for label, state in individual_lights if state == "on")
        unknown = sorted(label for label, state in individual_lights if state not in ("on", "off"))
        if on:
            reply = "Home Assistant reports these lights are on: " + ", ".join(on) + "."
        elif len(unknown) == len(individual_lights):
            reply = "I couldn't verify the state of any individual lights."
        elif unknown:
            reply = "None of the lights I could check are on."
        else:
            reply = "Home Assistant reports all individual lights are off."
        if unknown:
            reply += " I couldn't check: " + ", ".join(unknown) + "."
            return reply, "partial" if len(unknown) < len(individual_lights) else "unverified"
        return add_sass(reply, "lights_status", guest_mode), "confirmed"

    areas = None
    room_targets = set()

    def load_area_metadata():
        nonlocal areas
        areas = read_ha_areas(connection, origin_device)
    if origin_device is not None:
        load_area_metadata()
        if not areas:
            return "Which room do you mean? I couldn't verify the Assist device's area.", "unresolved"
        local_members = (lights.keys() & next(iter(areas.values()))) - light_groups
        if not local_members:
            return "Home Assistant didn't report any individual lights in this room.", "unresolved"
        if name == "some lights":
            off = sorted(entity for entity in local_members if lights[entity][1] == "off")
            if not off:
                if any(lights[entity][1] not in ("on", "off") for entity in local_members):
                    return "I couldn't verify any more lights to turn on in this room.", "unverified"
                return "All the lights I can see in this room are already on.", "confirmed"
            local_members = set(off[:2])

    def resolve(target, state, *, use_area=False):
        recovered = target.removeprefix(f"{state} ")
        matches = names.get(target) or names.get(recovered)
        if not matches and recovered in {"office light", "office lights"} and "light.study_light" in lights:
            matches = {"light.study_light"}
        if origin_device is not None:
            if recovered in {"lights", "all lights"} or recovered == name == "some lights":
                room_targets.add(target)
                return local_members
            return (matches or set()) & local_members
        if not use_area:
            return matches

        if areas is None:
            load_area_metadata()

        exception = re.fullmatch(r"everything except (?:the )?(.+)", recovered)
        if exception:
            excluded = areas.get(exception[1])
            if state != "off" or not excluded:
                return None
            members = (lights.keys() & set().union(*areas.values())) - excluded - light_groups
            room_targets.add(target)
            return members
        if recovered in areas:
            room_targets.add(target)
            return (lights.keys() & areas[recovered]) - light_groups
        if matches:
            return matches

        room_suffix = re.fullmatch(r"(.+?) in (?:the )?(.+)", recovered)
        if room_suffix and room_suffix[2] in areas:
            bare_name, area = room_suffix.groups()
        else:
            area = max((label for label in areas if recovered.startswith(label + " ")),
                       key=len, default=None)
            if area is None:
                return None
            bare_name = recovered[len(area) + 1:]
        if bare_name in {"lights", "all lights"}:
            members = (lights.keys() & areas[area]) - light_groups
            if members:
                room_targets.add(target)
            return members
        candidates = names.get(bare_name, set())
        in_area = candidates & areas[area]
        if in_area:
            return in_area
        # A unique light with no registered area can still have a spoken room qualifier.
        if len(candidates) == 1 and not any(candidates & entities for entities in areas.values()):
            return candidates
        return None

    # Prefer a full name, including names that contain "and".
    targets = [name] if name.startswith("everything except ") or resolve(name, desired_state) else re.split(
        r"\s*[,;]\s*|\s+(?:and then|as well as|and|then)\b\s*|\s+(?=turn (?:on|off)\b)",
        name,
    )
    resolved_targets = []
    skipped = []
    direction = desired_state
    for target in targets:
        target = target.strip().removeprefix("the ")
        if not target:
            continue
        explicit = (re.fullmatch(r"turn (on|off)(?: (?:the )?(.+))?", target)
                    or re.fullmatch(r"make (darker|brighter|very bright) (?:the )?(.+)", target))
        if explicit:
            direction, target = explicit.groups()
            if target is None:
                continue
        matches = resolve(target, direction, use_area=True)
        if not matches and not target.startswith("everything except "):
            words = target.split()
            splits = []
            for index in range(1, len(words)):
                left = " ".join(words[:index])
                right = " ".join(words[index:]).removeprefix("the ")
                left_matches = resolve(left, direction, use_area=True)
                right_matches = resolve(right, direction, use_area=True)
                if left_matches and right_matches:
                    splits.append(((left, left_matches), (right, right_matches)))
            if len(splits) > 1:
                skipped.append((f"I couldn't tell where to split {target}. Say 'and' between the light names.", "unresolved"))
                continue
            if splits:
                resolved_targets.extend((part, ids, direction) for part, ids in splits[0])
                continue
        resolved_targets.append((target, matches, direction))

    target_levels = {}

    def record_action(target, direction, status, *, entity=None, detail=None):
        if action_results is not None and len(action_results) < 200:
            percent = target_levels.get(entity, brightness)
            action_name = (f"set brightness to {percent}%" if percent is not None
                           else direction if direction in ("darker", "brighter", "very bright") else f"turn_{direction}")
            step = {"target": target, "action": action_name, "status": status}
            if entity is not None:
                step["entity_id"] = entity
            if detail is not None:
                step["detail"] = detail
            action_results.append(step)

    selected = {}
    room_off_entities = set()
    conflicts = set()
    for target, matches, direction in resolved_targets:
        if not matches:
            record_action(target, direction, "skipped", detail="unresolved")
            skipped.append((f"I couldn't find a Home Assistant light called {target}.", "unresolved"))
            continue
        if len(matches) > 1 and target not in room_targets:
            record_action(target, direction, "skipped", detail="ambiguous")
            options = ", ".join(sorted(matches))
            skipped.append((f"More than one light matches {target}. Try one of these entity IDs: {options}.", "unresolved"))
            continue
        for entity in sorted(matches):
            label, state = lights[entity]
            if state not in ("on", "off"):
                record_action(label, direction, "skipped", entity=entity, detail="unavailable")
                skipped.append((f"Home Assistant says {label} is unavailable.", "unavailable"))
                continue
            relative = direction in ("darker", "brighter")
            if (brightness is not None or relative or direction == "very bright") and entity not in dimmable:
                record_action(label, direction, "skipped", entity=entity, detail="brightness unsupported")
                skipped.append((f"Home Assistant doesn't report brightness control for {label}.", "unavailable"))
                continue
            percent = brightness
            goal = direction
            if direction == "very bright":
                percent, goal = 100, "on"
            elif relative:
                level = levels.get(entity)
                if state == "off" or not (isinstance(level, (int, float)) and 0 <= level <= 255):
                    reason = "already off" if state == "off" else "current brightness unknown"
                    record_action(label, direction, "skipped", entity=entity, detail=reason)
                    skipped.append((f"I left {label} alone ({reason}).", "unavailable"))
                    continue
                change = -relative_step if direction == "darker" else relative_step
                percent = min(100, max(1, round(level * 100 / 255) + change))
                goal = "on"
            if entity in conflicts:
                continue
            if entity in selected and (selected[entity][2], target_levels[entity]) != (goal, percent):
                del selected[entity]
                conflicts.add(entity)
                record_action(label, direction, "skipped", entity=entity, detail="conflicting directions")
                skipped.append((f"I heard conflicting settings for {label}. I left it alone.", "unresolved"))
                continue
            selected[entity] = (label, state, goal)
            target_levels[entity] = percent
            if direction == "off" and target in room_targets and not target.startswith("everything except "):
                room_off_entities.add(entity)

    skipped_details = "".join(f" {message}" for message, _ in skipped)
    if not selected:
        return (skipped_details.strip(), skipped[0][1]) if skipped else (
            "Tell me which lights to switch.", "unresolved"
        )
    if preview:
        for entity, (label, _, direction) in selected.items():
            record_action(label, direction, "planned", entity=entity)
        groups = {}
        for entity, (label, _, direction) in selected.items():
            groups.setdefault((direction, target_levels[entity]), []).append(label)
        plan = [f"set {', '.join(labels)} to {percent}%" if percent is not None
                else f"turn {direction} {', '.join(labels)}"
                for (direction, percent), labels in groups.items()]
        return f"Preview: I would {'; '.join(plan)}.{skipped_details}", "preview"
    if require_all and skipped:
        for entity, (label, _, direction) in selected.items():
            record_action(label, direction, "skipped", entity=entity, detail="incomplete correction")
        return f"I left the lights unchanged because I couldn't resolve the full correction.{skipped_details}", "unresolved"
    pending = {}
    verified = {(goal, target_levels[entity]): [] for entity, (_, _, goal) in selected.items()}

    def matches_goal(state, direction, level, percent):
        return state == direction and (
            percent is None or (isinstance(level, (int, float))
                                   and abs(level - round(percent * 255 / 100)) <= (0 if percent == 100 else 2))
        )

    already_set = set()
    for entity, (label, state, direction) in selected.items():
        # Reassert an explicit room shutdown even if HA already reports the lights off.
        if entity not in room_off_entities and matches_goal(state, direction, levels.get(entity), target_levels[entity]):
            already_set.add(entity)
            record_action(label, direction, "already_set", entity=entity)
    dispatch_deadline = monotonic() + 1.75
    for direction, percent in verified:
        entity_ids = [entity for entity, (_, _, goal) in selected.items()
                      if (goal, target_levels[entity]) == (direction, percent) and entity not in already_set]
        verified[direction, percent] = [label for entity, (label, _, goal) in selected.items()
                                        if (goal, target_levels[entity]) == (direction, percent) and entity in already_set]
        if not entity_ids:
            continue
        labels = ", ".join(selected[entity][0] for entity in entity_ids)
        data = {"entity_id": entity_ids[0] if len(entity_ids) == 1 else entity_ids}
        if percent is not None:
            data["brightness_pct"] = percent
        remaining = dispatch_deadline - monotonic()
        if remaining <= 0:
            for entity in entity_ids:
                record_action(selected[entity][0], direction, "skipped", entity=entity, detail="dispatch time limit")
            skipped.append((f"I ran out of time before sending the command for {labels}.", "unverified"))
            continue
        action = Request(
            f"{url}/api/services/light/turn_{direction}",
            data=json.dumps(data).encode(),
            headers=headers, method="POST",
        )
        try:
            with opener.open(action, timeout=min(remaining, 1)):
                pass
        except HTTPError as error:
            error.close()
            for entity in entity_ids:
                record_action(selected[entity][0], direction, "failed", entity=entity, detail=f"HTTP {error.code}")
            skipped.append((f"Home Assistant returned HTTP {error.code} for {labels}.", "action_error"))
            continue
        except OSError:
            for entity in entity_ids:
                record_action(selected[entity][0], direction, "unverified", entity=entity, detail="no dispatch response")
            skipped.append((f"I didn't get a response for {labels}.", "unverified"))
            continue
        pending.update({entity: direction for entity in entity_ids})

    deadline = monotonic() + 3
    last_reported = {}
    while pending and monotonic() < deadline:
        for entity, direction in tuple(pending.items()):
            remaining = deadline - monotonic()
            if remaining <= 0:
                break
            request = Request(f"{url}/api/states/{entity}", headers=headers)
            try:
                with opener.open(request, timeout=min(remaining, 0.5)) as response:
                    observed = json.loads(response.read(65536))
                    state = observed["state"]
                    attributes = observed.get("attributes")
                    level = attributes.get("brightness") if isinstance(attributes, dict) else None
                    percent = target_levels[entity]
                    last_reported[entity] = f"{state}, brightness {round(level * 100 / 255)}%" if (
                        percent is not None and isinstance(level, (int, float)) and 0 <= level <= 255
                    ) else state
                    if matches_goal(state, direction, level, percent):
                        verified[direction, percent].append(selected[entity][0])
                        record_action(selected[entity][0], direction, "confirmed", entity=entity)
                        del pending[entity]
            except HTTPError as error:
                error.close()
            except (OSError, ValueError, KeyError, TypeError):
                pass
        if pending:
            sleep(min(0.25, max(0, deadline - monotonic())))
    for entity, direction in pending.items():
        label = selected[entity][0]
        state = last_reported.get(entity, "no state reported")
        record_action(label, direction, "unverified", entity=entity, detail=str(state))
        percent = target_levels[entity]
        goal = f"at {percent}%" if percent is not None else direction
        skipped.append((f"I couldn't confirm {label} is {goal} ({state}).", "unverified"))
    confirmations = [
        f"{', '.join(labels)} {'is' if len(labels) == 1 else 'are'} "
        + (f"at {percent}%." if percent is not None else f"{direction}.")
        for (direction, percent), labels in verified.items() if labels
    ]
    reply = " ".join(confirmations + [message for message, _ in skipped])
    outcome = ("partial" if confirmations else skipped[0][1]) if skipped else "confirmed"
    if outcome == "partial" and room_targets:
        reply = add_sass("I handled part of that. Some lighting changes couldn't be confirmed.",
                         "partial_lighting", guest_mode)
    if outcome == "confirmed":
        if room_targets:
            reply = "Done."
        directions = {direction for direction, _ in verified}
        percents = {percent for _, percent in verified if percent is not None}
        if len(already_set) == len(selected):
            category = "already_set"
        elif len(directions) > 1:
            category = "mixed_lighting"
        elif percents:
            category = "full_brightness" if percents == {100} else "brightness"
        else:
            category = "lights_on" if "on" in directions else "lights_off"
        reply = add_sass(reply, category, guest_mode)
    return reply, outcome


def converse(message, session_id, routine_reply=None, *, lighting_context=None, scope=None, guest_mode=None):
    now = monotonic()
    while SESSIONS and now - next(iter(SESSIONS.values()))["at"] >= IDLE_SECONDS:
        SESSIONS.popitem(last=False)
    state = SESSIONS.pop(session_id, None)
    if state is None:
        session_id = secrets.token_urlsafe(24)
        state = {"last": None, "name": None}
    command = message.casefold().strip(" .?!")
    name = NAME_PATTERN.fullmatch(message.strip(" .?!"))
    kind = CHAT_COMMANDS.get(command)
    if routine_reply is not None:
        reply = routine_reply
    elif name:
        state["name"] = name[1].strip()
        reply = add_sass(f"Nice to meet you, {state['name']}.", "greeting", guest_mode)
    elif kind == "recall_name":
        reply = f"Your name is {state['name']}." if state["name"] else "I don't know your name yet."
        if state["name"]:
            reply = add_sass(reply, "memory", guest_mode)
    elif kind == "recall_message":
        reply = f"You said: {state['last']}" if state["last"] else "This is your first message."
        if state["last"]:
            reply = add_sass(reply, "memory", guest_mode)
    elif kind == "time":
        reply = add_sass(f"It's {datetime.now().astimezone():%H:%M} here.", "time", guest_mode)
    elif kind == "greeting":
        reply = f"Hello, {state['name']}." if state["name"] else "Hello. I'm Declan."
        reply = add_sass(reply, "greeting", guest_mode)
    else:
        reply = UNMATCHED_REPLY
    state.update(last=message, at=now)
    if lighting_context is not None:
        state["lighting_context"] = lighting_context
        state["lighting_scope"] = scope
    SESSIONS[session_id] = state
    if len(SESSIONS) > 128:
        SESSIONS.popitem(last=False)
    return {"session_id": session_id, "reply": reply}


@diagnostics.timed("ha_transcription")
def traced_transcribe(*args, **kwargs):
    return web_stt.transcribe(*args, **kwargs)

class Handler(BaseHTTPRequestHandler):
    timeout = 5

    def end_headers(self):
        for name, value in response_headers(ingress=hasattr(self, 'headers') and self.has_ingress_access(),
                                            nonce=getattr(self, '_page_nonce', None)).items():
            self.send_header(name, value)
        super().end_headers()

    def send_body(self, status, data, content_type, filename=None):
        self._page_nonce = None
        if content_type.startswith('text/html'):
            data, self._page_nonce = secure_page(data)
        trace = diagnostics.ACTIVE.get()
        if trace is not None:
            if trace['outcome'] == 'unknown':
                trace['outcome'] = 'failed' if status >= 400 else 'completed'
            diagnostics.persist(trace)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if self.path == "/health":
            self.send_header("X-Declan-Pid", str(os.getpid()))
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, status, data):
        trace = diagnostics.ACTIVE.get()
        if trace is not None:
            trace['outcome'] = data.get('outcome') or ('failed' if status >= 400 else 'completed')
            data = {**data, 'diagnostic_id': trace['id']}
        self.send_body(status, json.dumps(data).encode(), "application/json")

    def spotify_settings(self, body=None):
        try:
            if body is not None:
                music.save_spotify_credentials(body.get("client_id"), body.get("client_secret"))
                source = "saved"
            else:
                _, source = music.spotify_credentials()
        except (OSError, ValueError) as error:
            if body is not None and isinstance(error, ValueError):
                self.send_json(400, {"error": "Enter both a valid Spotify Client ID and Client Secret."})
            else:
                self.send_json(503, {"error": "Spotify settings are unavailable."})
            return
        self.send_json(200, {"source": source})

    def has_ingress_access(self):
        token = os.environ.get("DECLAN_INGRESS_TOKEN", "")
        supplied = self.headers.get("X-Declan-Ingress-Token", "")
        return (len(token) >= 32 and token != os.environ.get("DECLAN_ASSIST_TOKEN", "")
                and secrets.compare_digest(supplied.encode(), token.encode()))

    def approved_player_settings(self, body=None):
        connection = ha_device_connection()
        if connection is None:
            self.send_json(503, {"error": "Home Assistant is not configured."})
            return
        inventory, error = read_music_inventory(connection)
        if error:
            self.send_json(503, {"error": "Home Assistant media inventory is unavailable."})
            return
        areas = read_ha_areas(connection)
        if not areas:
            self.send_json(503, {"error": "Home Assistant areas are unavailable."})
            return
        candidates = {row["entity_id"]: row for row in inventory
                      if row.get("declan_music_assistant") is True
                      and row["entity_id"].startswith("media_player.")}
        rooms = sorted({music.room_key(name) for name in areas} | {"everywhere"})
        if body is not None:
            selected = body.get("rooms") if isinstance(body, dict) else None
            if not isinstance(selected, dict) or any(
                not isinstance(key, str) or key not in rooms
                or not isinstance(value, str) or value not in candidates
                for key, value in selected.items()
            ):
                self.send_json(400, {"error": "Select registered Music Assistant players for known Home Assistant areas."})
                return
            try:
                approved_media_players.save(selected)
            except (OSError, ValueError):
                self.send_json(503, {"error": "Could not save approved players."})
                return
        try:
            configured = approved_media_players.load()
        except (OSError, ValueError):
            self.send_json(503, {"error": "Approved media player configuration is invalid."})
            return
        self.send_json(200, {
            "configured": configured is not None,
            "rooms": rooms,
            "selected": configured or {},
            "players": [
                {"entity_id": entity,
                 "name": (row.get("attributes") or {}).get("friendly_name") or entity,
                 "area": row.get("declan_area") or "",
                 "state": row.get("state")}
                for entity, row in sorted(candidates.items())
            ],
        })

    def do_GET(self):
        ingress = self.has_ingress_access()
        if not ingress and self.client_address[0] != "127.0.0.1":
            self.send_json(403, {"error": "Local access only."})
            return
        if not ingress and (
            self.path.startswith("/api/history")
            or self.path.startswith("/api/settings/") or self.path in {"/api/voice-profiles", "/api/voicepipeline"}
            or self.path in {"/api/diagnostics", "/api/settings/spotify", "/api/updates", "/api/updates/status"}
        ) and self.headers.get("Host") not in {
            f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"
        }:
            self.send_json(403, {"error": "Use the local Declan address."})
            return
        if self.path == "/":
            if not ingress:
                self.send_json(404, {"error": "Declan is managed through the Home Assistant app."})
                return
            page = Path(__file__).with_name("index.html").read_bytes()
            self.send_body(200, page, "text/html; charset=utf-8")
        elif self.path == "/logo.png":
            self.send_body(200, Path(__file__).with_name("logo.png").read_bytes(), "image/png")
        elif self.path == "/health":
            self.send_json(200, {"status": "ok"})
        elif self.path == "/api/ha-status":
            self.send_json(200, {"status": home_assistant_status(), "release_version": RELEASE_VERSION})
        elif self.path == "/api/updates/status":
            self.send_json(200, {**updates.status(), "current": RELEASE_VERSION})
        elif self.path == "/api/updates":
            try:
                self.send_json(200, {**updates.status(), "current": RELEASE_VERSION, "versions": updates.check()})
            except (OSError, ValueError, subprocess.SubprocessError):
                self.send_json(503, {"error": "Couldn't check GitHub for releases."})
        elif self.path in {"/api/settings/export", "/api/settings/export-learning", "/api/settings/recovery", "/api/settings/recovery-learning"}:
            try:
                document = (configuration.recovery(self.path.endswith("recovery-learning")) if "/recovery" in self.path else
                            configuration.export(self.path.endswith('export-learning')))
                self.send_body(200, json.dumps(document).encode(), 'application/json', 'declan-settings.json')
            except (ValueError, OSError, sqlite3.Error):
                self.send_json(503, {"error": "Settings export is unavailable."})
        elif self.path == "/api/voicepipeline":
            try:
                self.send_json(200, voicepipeline.listing())
            except voicepipeline.PipelineError as error:
                self.send_json(error.status, {'error': str(error)})
        elif self.path == "/api/voice-profiles":
            try:
                self.send_json(200, voice_profiles.listing())
            except (OSError, sqlite3.Error):
                self.send_json(503, {'error': 'Voice profiles are unavailable.'})
        elif self.path == "/api/diagnostics":
            try:
                self.send_json(200, {"traces": diagnostics.recent()})
            except (OSError, sqlite3.Error, ValueError):
                self.send_json(503, {"error": "Diagnostics are unavailable."})
        elif self.path == "/api/settings/spotify":
            self.spotify_settings()
        elif self.path == "/api/settings/media-players":
            self.approved_player_settings()
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
                aliases = history.learned_intents() if before is None else None
                for turn in turns:
                    turn["teachable"] = (turn["source"] in {"assist", "browser_voice"} and not turn["outcome"]
                                         and turn["reply"] == UNMATCHED_REPLY
                                         and 0 < len(history.normalize_phrase(turn["message"])) <= 120)
            except ValueError:
                self.send_json(400, {"error": "Invalid history cursor."})
                return
            except (OSError, sqlite3.Error):
                self.send_json(503, {"error": "Conversation history is unavailable."})
                return
            self.send_json(200, {
                "turns": turns[:50], "next": turns[49]["id"] if len(turns) > 50 else None,
                "learned_intents": aliases,
            })
        else:
            self.send_json(404, {"error": "Not found."})

    def transcribe_browser_audio(self):
        if self.headers.get_content_type() != "application/octet-stream":
            self.send_json(415, {"error": "Expected microphone audio."})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= web_stt.MAX_AUDIO_BYTES or size % 2:
                raise ValueError
        except ValueError:
            self.send_json(400, {"error": "Record up to 20 seconds of microphone audio."})
            return
        connection = ha_device_connection()
        if connection is None:
            self.send_json(503, {"error": "Home Assistant isn't configured."})
            return
        audio = self.rfile.read(size)
        if len(audio) != size:
            self.send_json(400, {"error": "The microphone recording was incomplete."})
            return
        try:
            text = traced_transcribe(connection[0], os.environ["DECLAN_HA_TOKEN"].strip(), audio,
                                      pipeline=configuration.get("DECLAN_WEB_ASSIST_PIPELINE", "").strip())
        except ImportError:
            self.send_json(503, {"error": "Install requirements-web-voice.txt to enable the Assist microphone."})
            return
        except web_stt.AssistSpeechError as error:
            print(f"Web Assist transcription failed: {error.code}", flush=True)
            self.send_json(502, {"error": f"Home Assistant speech recognition failed ({error.code})."})
            return
        except (OSError, ValueError, AttributeError, TypeError) as error:
            print(f"Web Assist connection or protocol failure: {type(error).__name__}", flush=True)
            self.send_json(502, {"error": "Home Assistant couldn't transcribe that recording."})
            return
        self.send_json(200, {"text": text})

    def do_POST(self):
        if self.path not in {"/api/chat", "/api/assist", "/api/stt", "/api/tts", "/api/assist/history"}:
            return self.handle_post()
        with diagnostics.request(self.path):
            return self.handle_post()

    def handle_post(self):
        if self.path in {"/api/assist", "/api/assist/history"}:
            token = os.environ.get("DECLAN_ASSIST_TOKEN", "")
            supplied = self.headers.get("Authorization", "")
            valid = bool(token) and secrets.compare_digest(supplied.encode(), f"Bearer {token}".encode())
            retry = self.server.bad_tokens.check(self.client_address[0], valid)
            if retry:
                self.close_connection = True
                self.send_response(429)
                self.send_header('Retry-After', str(retry))
                self.send_header('Content-Length', '0')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                return
            if not valid:
                self.close_connection = True
                self.send_json(401, {"error": "Invalid bridge credentials."})
                return
        elif self.path not in {"/api/chat", "/api/settings/spotify", "/api/tts", "/api/stt", "/api/updates", "/api/history/clear", "/api/history/intents", "/api/settings/import", "/api/settings/media-players", "/api/voice-profiles", "/api/voicepipeline"}:
            self.send_json(404, {"error": "Not found."})
            return
        elif not self.has_ingress_access() and (
            self.client_address[0] != "127.0.0.1" or self.headers.get("Origin") not in {
                f"http://127.0.0.1:{self.server.server_port}",
                f"http://localhost:{self.server.server_port}",
            }
        ):
            self.send_json(403, {"error": "Send requests from the local Declan page."})
            return
        if self.path == "/api/stt":
            self.transcribe_browser_audio()
            return
        if self.headers.get_content_type() != "application/json":
            self.send_json(415, {"error": "Send application/json."})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            max_size = 450000 if self.path == "/api/voice-profiles" else 196608 if self.path == "/api/settings/import" else 65536 if self.path == "/api/assist/history" else 8192
            if not 0 < size <= max_size:
                raise ValueError
            body = json.loads(self.rfile.read(size))
            if self.path == "/api/settings/media-players":
                self.approved_player_settings(body)
                return
            if self.path == "/api/voicepipeline":
                try:
                    self.send_json(200, voicepipeline.manage(body))
                except voicepipeline.PipelineError as error:
                    self.send_json(error.status, {'error': str(error)})
                except ValueError as error:
                    self.send_json(400, {'error': str(error)})
                return
            if self.path == "/api/voice-profiles":
                try:
                    if isinstance(body, dict) and body.get('operation') in {'create', 'save_sample'}:
                        raise ValueError('Use Voice profiles to enrol through VoicePipeline. Separate local collection is retired.')
                    self.send_json(200, voice_profiles.manage(body))
                except ValueError as error:
                    self.send_json(400, {'error': str(error)})
                except (OSError, sqlite3.Error):
                    self.send_json(503, {'error': 'Voice profiles could not be saved.'})
                return
            if self.path == "/api/settings/import":
                try:
                    if not isinstance(body, dict) or set(body) - {'document', 'confirm', 'expected'}:
                        raise ValueError('Send a settings file to preview.')
                    if body.get('confirm') is True:
                        configuration.apply(body.get('document'), body.get('expected'))
                        self.send_json(200, {'saved': True})
                    elif 'confirm' not in body:
                        self.send_json(200, configuration.preview(body.get('document')))
                    else:
                        raise ValueError('Preview the settings before confirming.')
                except ValueError as error:
                    self.send_json(400, {'error': str(error)})
                except (OSError, sqlite3.Error):
                    self.send_json(503, {'error': 'Settings could not be imported.'})
                return
            if self.path == "/api/history/intents":
                try:
                    if not isinstance(body, dict):
                        raise ValueError("Send an intent correction or removal.")
                    if set(body) == {"forget"} and isinstance(body["forget"], str) and 0 < len(body["forget"]) <= 120:
                        history.forget_intent(body["forget"])
                    elif set(body) == {"phrase", "target", "previous"}:
                        history.edit_intent(body["phrase"], body["target"], body["previous"])
                    elif (set(body) == {"turn_id", "target"} and type(body["turn_id"]) is int
                          and 0 < body["turn_id"] < 2**63 and isinstance(body["target"], str)
                          and 0 < len(body["target"]) <= 120):
                        history.teach_intent(body["turn_id"], body["target"], UNMATCHED_REPLY)
                    else:
                        raise ValueError("Choose a missed voice command and enter what you meant.")
                except ValueError as error:
                    self.send_json(400, {"error": str(error)})
                    return
                except (OSError, sqlite3.Error):
                    self.send_json(503, {"error": "Intent corrections are unavailable."})
                    return
                self.send_json(200, {"saved": True})
                return
            if self.path == "/api/history/clear":
                if not isinstance(body, dict) or body.get("confirm") is not True:
                    self.send_json(400, {"error": "Confirm before clearing conversation history."})
                    return
                try:
                    deleted = history.clear()
                except (OSError, sqlite3.Error):
                    self.send_json(503, {"error": "Conversation history could not be cleared."})
                    return
                self.send_json(200, {"deleted": deleted})
                return
            if self.path == "/api/updates":
                try:
                    if isinstance(body, dict) and body.get('operation') == 'check':
                        versions = updates.check(body.get('include_prereleases', False))
                        self.send_json(200, {**updates.status(), 'current': RELEASE_VERSION,
                                             'versions': versions, 'prereleases': updates.prerelease_versions()})
                        return
                    updates.queue(body.get("version") if isinstance(body, dict) else None, RELEASE_VERSION,
                                  body.get('include_prereleases', False) if isinstance(body, dict) else False)
                except ValueError as error:
                    self.send_json(409, {"error": str(error)})
                    return
                except (OSError, subprocess.SubprocessError):
                    self.send_json(503, {'error': "Couldn't check GitHub for releases."})
                    return
                self.send_json(202, {"status": "installing"})
                return
            if self.path == "/api/settings/spotify":
                if not isinstance(body, dict):
                    raise ValueError
                self.spotify_settings(body)
                return
            message = body["message"].strip()
            session_id = body.get("session_id")
            if not 0 < len(message) <= 1000:
                raise ValueError
            if session_id is not None and (not isinstance(session_id, str) or len(session_id) > 64):
                raise ValueError
        except (ValueError, TypeError, KeyError, AttributeError):
            detail = ("Send valid Spotify settings." if self.path == "/api/settings/spotify"
                      else "Send valid history confirmation." if self.path == "/api/history/clear"
                      else "Send a message of 1 to 1,000 characters.")
            self.send_json(400, {"error": detail})
            return
        if self.path == "/api/tts":
            audio = render_web_voice(message)
            if audio is None:
                self.send_json(503, {"error": "Declan's voice is unavailable."})
            else:
                self.send_body(200, audio, "audio/mpeg")
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
                    routine_action_results(body.get("steps")),
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
        action_results = []
        light_result = None
        scope = source
        origin_device = None
        satellite = body.get("satellite_id") if source == "assist" else None
        if (not isinstance(satellite, str) or len(satellite) > 128
                or not re.fullmatch(r"assist_satellite\.[a-z0-9_]+", satellite)):
            satellite = None
        if source == "assist":
            device_id = body.get("device_id")
            user_id = body.get("user_id")
            origin = tuple(value if isinstance(value, str) and 0 < len(value) <= 128 else None
                           for value in (device_id, user_id))
            origin_device = origin[0]
            scope = (source, *origin, satellite) if any(origin) or satellite else None
        if source == "assist":
            speaker = body.get("speaker")
            speaker_name = (speaker.get("name") if isinstance(speaker, dict)
                            and type(speaker.get("confidence")) in (int, float)
                            and speaker["confidence"] >= 0.75 and isinstance(speaker.get("name"), str) else None)
            if not CAPTURE_ARBITER.claim(history.normalize_phrase(message), satellite or origin_device,
                                         body.get("capture"), speaker_name):
                self.send_json(200, {"reply": "", "session_id": session_id or secrets.token_urlsafe(24),
                                     "outcome": "duplicate"})
                return
        last_lights = ()
        last_device = None
        last_information = None
        with SESSION_LOCK:
            previous = SESSIONS.get(session_id)
            if (scope is not None and previous and previous.get("device_status_scope") == scope
                    and monotonic() - previous["at"] < IDLE_SECONDS):
                last_device = previous.get("device_status_target")
            if (scope is not None and previous and previous.get("lighting_scope") == scope
                    and monotonic() - previous["at"] < IDLE_SECONDS):
                last_lights = previous.get("lighting_context", ())
            if (scope is not None and previous and previous.get("information_scope") == scope
                    and monotonic() - previous["at"] < IDLE_SECONDS):
                last_information = previous.get("information_context")
        lighting_context = None
        status_target = None
        information_context = None
        phrase = history.normalize_phrase(message)
        effective_message = message
        if source in {"assist", "browser_voice"} and len(phrase) <= 120:
            try:
                target = history.learned_intent(phrase)
            except (OSError, sqlite3.Error):
                self.log_error("Could not look up learned intention; using the original transcript.")
                target = None
            if isinstance(target, str) and 0 < len(target) <= 120:
                # Interpret once through the normal handlers. Never follow alias chains.
                effective_message = target
                phrase = history.normalize_phrase(target)
        opener = build_opener(ProxyHandler({}), NoRedirect())
        timer_result = timers.handle(
            phrase, opener,
            satellite=satellite if isinstance(satellite, str) and len(satellite) <= 128 else None,
            device=origin_device, browser=source != "assist",
        )
        if timer_result:
            routine_reply, outcome = timer_result
            if outcome in ("timer_set", "timer_adjusted", "timer_cancelled", "timer_stopped"):
                routine_reply = add_sass(routine_reply, outcome, read_guest_mode())
        elif phrase == "stop":
            routine_reply, outcome, routine_status = stop_origin_output(ha_device_connection(), satellite, origin_device)
        elif phrase.replace("’", "'") in DINNER_PHRASES:
            routine_reply, outcome = start_dinner(ha_device_connection())
        elif phrase in SEXY_TIME_COMMANDS:
            routine_reply, outcome, routine_status = run_sexy_time(SEXY_TIME_COMMANDS[phrase], ha_device_connection())
        elif phrase in GUEST_COMMANDS:
            routine_reply, outcome = guest_assignment(GUEST_COMMANDS[phrase], ha_device_connection())
        elif routine_turn := select_routine_turn(phrase, origin_device or satellite):
            lighting_context = ()
            routine, follow_on = routine_turn
            routine_reply, outcome, routine_status = execute_routine(routine, action_results)
            if follow_on:
                light_steps = []
                if follow_on.startswith("play "):
                    command = music.parse(follow_on)
                    follow_reply, follow_outcome = (
                        music.play(command, ha_device_connection(), read_music_inventory,
                                   **({"origin": satellite or origin_device} if satellite or origin_device else {})) if command
                        else ("Tell me where to play the music.", "unresolved")
                    )
                else:
                    follow_result = handle_light_request(
                        follow_on, action_results=light_steps, last_lights=last_lights,
                        origin_device=origin_device or satellite,
                    )
                    follow_reply, follow_outcome = follow_result or (
                        "I couldn't understand the lighting command after the routine.", "unresolved"
                    )
                action_results.extend(light_steps)
                if follow_outcome == "confirmed" and scope is not None and len(light_steps) < 200:
                    lighting_context = tuple(dict.fromkeys(
                        step["entity_id"] for step in light_steps
                        if step["status"] in ("confirmed", "already_set") and "entity_id" in step
                    ))
                if routine_status and routine_status not in routine_reply:
                    routine_reply += f" {routine_status}"
                routine_reply += f" {follow_reply}"
                outcome = chained_outcome(outcome, follow_outcome)
        else:
            information_phrase, clarification = conditions.follow_up(phrase, last_information)
            condition_result = conditions.handle(information_phrase, opener) if not clarification else None
            if clarification:
                routine_reply, outcome = clarification, "unresolved"
            elif condition_result:
                routine_reply, outcome, category = condition_result
                if outcome in ("confirmed", "partial", "unavailable"):
                    information_context = conditions.question_context(information_phrase)
                if outcome == "confirmed":
                    routine_reply = add_sass(routine_reply, category, read_guest_mode())
            elif status_query := device_status.parse(phrase, last_device):
                connection = ha_device_connection()
                if connection is None:
                    routine_reply, outcome = "The Home Assistant connection isn't configured.", "not_configured"
                else:
                    inventory, error = read_ha_inventory(connection)
                    if error:
                        routine_reply, outcome = "I couldn't read device states from Home Assistant.", error
                    else:
                        routine_reply, outcome, status_target = device_status.describe(*status_query, inventory)
                        if outcome == "confirmed":
                            guest_mode = next(
                                (item.get("state") for item in inventory if isinstance(item, dict)
                                 and item.get("entity_id") == GUEST_MODE_ENTITY), None
                            )
                            routine_reply = add_sass(routine_reply, "device_status", guest_mode)
            elif music_feedback := music.parse_feedback(phrase):
                routine_reply, outcome = music.feedback(music_feedback, ha_device_connection(), read_music_inventory)
            elif music_control := music.parse_control(phrase):
                routine_reply, outcome = music.control(
                    music_control, ha_device_connection(), read_music_inventory,
                    origin=origin_device or satellite, read_areas=read_ha_areas, assist=source == "assist",
                )
            elif music_command := music.parse(phrase):
                routine_reply, outcome = music.play(
                    music_command, ha_device_connection(), read_music_inventory,
                    **({"origin": satellite or origin_device} if satellite or origin_device else {}),
                )
            else:
                media_result = search_media(phrase)
                if media_result:
                    routine_reply, outcome = media_result
                else:
                    light_result = handle_light_request(phrase, action_results=action_results,
                                                        last_lights=last_lights, origin_device=origin_device)
            if light_result:
                routine_reply, outcome = light_result
                if not re.match(r"^(?:preview|dry[ -]run)\b", phrase):
                    lighting_context = tuple(dict.fromkeys(
                        step["entity_id"] for step in action_results
                        if step["status"] in ("confirmed", "already_set") and "entity_id" in step
                    )) if outcome == "confirmed" and scope is not None and len(action_results) < 200 else ()
        chat_kind = effective_message.casefold().strip(" .?!")
        guest_mode = None
        if routine_reply is None and (chat_kind in CHAT_COMMANDS or NAME_PATTERN.fullmatch(chat_kind)):
            guest_mode = read_guest_mode()
            if CHAT_COMMANDS.get(chat_kind) == "time":
                information_context = ("time", None, None)
        with SESSION_LOCK:
            previous = SESSIONS.get(session_id)
            failed_phrase = previous.get("failed_light_phrase") if previous else None
            actions = {step["action"] for step in action_results if "action" in step}
            phrase_suggestion = None
            if (light_result and outcome == "confirmed" and actions and scope is not None
                    and failed_phrase and failed_phrase["scope"] == scope
                    and monotonic() - previous["at"] <= 30
                    and actions & failed_phrase["actions"]
                    and failed_phrase["text"].casefold() != message.casefold()):
                phrase_suggestion = failed_phrase["text"]
            reply = converse(effective_message, session_id, routine_reply, lighting_context=lighting_context,
                             scope=scope, guest_mode=guest_mode)
            if outcome:
                reply["outcome"] = outcome
            if routine_status:
                reply["routine_status"] = routine_status
            session = SESSIONS[reply["session_id"]]
            session["last"] = message
            session["device_status_target"] = status_target
            session["device_status_scope"] = scope
            session["information_context"] = information_context
            session["information_scope"] = scope
            session.pop("failed_light_phrase", None)
            if (light_result and outcome == "unresolved" and scope is not None
                    and not re.match(r"^(?:preview|dry[ -]run)\b", phrase)
                    and any(step.get("detail") == "unresolved" for step in action_results)):
                session["failed_light_phrase"] = {"text": message, "scope": scope, "actions": actions}
            try:
                history.record(reply["session_id"], source, message, reply["reply"], outcome, routine_status,
                               action_results, phrase_suggestion, speaker=body.get("speaker") if source == "assist" else None,
                               diagnostic_id=diagnostics.current_id())
                if action_results:
                    reply["action_results"] = action_results
            except (OSError, sqlite3.Error):
                self.log_error("Could not save conversation history.")
                reply["history_saved"] = False
        self.send_json(200, reply)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
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
    history.retention_seconds()  # Reject invalid retention before accepting requests.
    history.initialize()
    timers.initialize()
    bind_address = "0.0.0.0" if args.assist_lan else "127.0.0.1"
    if args.assist_lan:
        bind_address = os.environ.get('DECLAN_BIND_ADDRESS', bind_address)
        try:
            address = ipaddress.ip_address(bind_address)
            if address.version != 4:
                raise ValueError
        except ValueError:
            parser.error('DECLAN_BIND_ADDRESS must be an IPv4 address.')
    try:
        server = ThreadingHTTPServer((bind_address, port), Handler)
    except OSError as error:
        parser.exit(1, f"Declan could not open port {port}: {error}\n")
    with server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        next_prune = monotonic()
        next_music_check = monotonic() + 5
        url = f"http://127.0.0.1:{server.server_port}"
        try:
            opener = build_opener(ProxyHandler({}))
            with opener.open(url + "/health", timeout=3) as response:
                if json.load(response) != {"status": "ok"}:
                    raise ValueError("Unexpected health response.")
            print(f"Declan 2.0 API is ready at {url}/health", flush=True)
            while worker.is_alive():
                worker.join(timeout=0.5)
                if updates.RESTART.is_set():
                    print("Restarting Declan to activate the selected release.", flush=True)
                    raise SystemExit(75)
                try:
                    timers.ring_due(opener)
                except Exception:
                    logging.exception("Timer alarms could not be checked.")
                if monotonic() >= next_music_check:
                    next_music_check = monotonic() + 5
                    try:
                        music.skip_blocked_tracks(ha_device_connection(), read_music_inventory)
                    except Exception:
                        logging.exception("Blocked music could not be checked.")
                if monotonic() >= next_prune:
                    try:
                        history.prune()
                    except Exception:
                        logging.exception("Conversation history could not be pruned.")
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

