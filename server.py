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
from contextlib import contextmanager
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from arbitration import CaptureArbiter

import conditions
import sensitive_confirmations
import diagnostics
import declan_logs
import configuration
DECLAN_EVENT_LOG = logging.getLogger("declan.server")
DECLAN_EVENT_LOG.setLevel(logging.INFO)
import voice_profiles
import voicepipeline
import device_status
import retry_learning
import retry_training_persistence
import conversation_persistence
import turn_finalization
import turn_response_orchestration
import turn_persistence_orchestration
import request_origin
import request_validation
import session_context_retrieval
import retry_context
import retry_cancellation
import learned_intent_resolution
import sensitive_confirmation_response
import sensitive_confirmation_decision
import sensitive_confirmation_turn
import routine_preview_detection
import routine_preview_dispatch
import early_command_result
import stop_result_response
import roast_guest_dispatch
import routine_registry_dispatch
import routine_follow_on_dispatch
import information_result_response
import device_result_response
import lighting_result_dispatch
import fallback_orchestration
import guest_assignment_command
import roast_command_dispatch
import timer_command_dispatch
import stop_command_dispatch
import information_command_dispatch
import device_command_dispatch
import lighting_command_dispatch
import lighting_context_finalization
import fallback_entity_authorization
import guarded_fallback_dispatch
import response_persona_context
import turn_context_preparation
import turn_response_composition
import turn_persistence_dispatch
import history
import music
import approved_media_players
import spotify_playlists
import timers
import updates
import web_stt
import openai_planner
import ai_settings
import ai_credentials
import ai_pricing
import ai_budget
import ai_context
import ai_intent_gate
import guarded_fallback
import ha_dispatcher
import routine_registry
import script_discovery
from intent_preprocessing import preprocess_speech
from personality import add_sass, choose_line
import routine_responses
import routine_follow_on
import response_composition
import command_responses
import command_registry
import session_orchestration
import session_turn_state
import lighting_intents
import roast
import personality_policy


SESSIONS = OrderedDict()
SESSION_LOCK = Lock()
CAPTURE_ARBITER = CaptureArbiter()
SENSITIVE_CONFIRMATIONS = sensitive_confirmations.ConfirmationGate()
ROUTINE_LOCKS = {name: Lock() for name in ("morning", "night", "movie")}
ROUTINE_LOCKS["movie_bedroom"] = Lock()
routine_last_attempts = {}
ACTIVE_ROUTINES = {}
ACTIVE_ROUTINES_LOCK = Lock()

@contextmanager
def track_routine(name, script):
    with ACTIVE_ROUTINES_LOCK:
        ACTIVE_ROUTINES[name] = script
    try:
        yield
    finally:
        with ACTIVE_ROUTINES_LOCK:
            ACTIVE_ROUTINES.pop(name, None)

def stop_pending_routines():
    connection = ha_device_connection()
    if connection is None:
        return "Home Assistant is not connected.", "not_configured", None
    with ACTIVE_ROUTINES_LOCK:
        active = dict(ACTIVE_ROUTINES)
    if not active:
        return "No mapped routine is currently awaiting completion.", "confirmed", None
    url, headers, opener = connection
    stopped, unknown = [], []
    for name, script in active.items():
        request = Request(f"{url}/api/services/script/turn_off", headers=headers,
                          data=json.dumps({"entity_id": script}).encode(), method="POST")
        try:
            with opener.open(request, timeout=4) as response:
                response.read(4096)
            stopped.append(name)
        except HTTPError as error:
            error.close()
            unknown.append(name)
        except (OSError, ValueError):
            unknown.append(name)
    message = ("Cancellation requested for: " + ", ".join(stopped) + ". " if stopped else "")
    if unknown:
        message += "Could not confirm cancellation request for: " + ", ".join(unknown) + "."
    message += " Already completed actions were not rolled back."
    return message, "unverified" if unknown or stopped else "confirmed", None

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
DINNER_PHRASES = {
    "dinner is served", "it's dinner time", "time for dinner", "it's time for dinner",
    "announce dinner", "start dinner time", "dinner time",
}
GUEST_MODE_ENTITY = "input_boolean.guest_mode"
GUEST_REGISTER_ENTITY = "input_text.guests_in_charge"
VISITORS_PRESENT_ENTITY = "input_boolean.visitors_present"  # fallback when no explicit mapping exists
GUEST_COMMANDS = {
    "who's in charge": "check",
    "who is in charge of the house": "check",
    "who is looking after the house tonight": "check",
    "who is in charge": "check",
    "who is looking after the house": "check",
    "the guests have left": "clear",
    "our guests have left": "clear",
    "all guests have left": "clear",
    "all guest have left": "clear",
    "the guest has left": "clear",
    "our guest has left": "clear",
    "guests have left": "clear",
    "guest has left": "clear",
    "everyone has left": "clear",
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


def read_visitors_present():
    """Visitor presence is independent of guest authority.

    Missing or unavailable state is unknown and therefore privacy-safe.
    """
    url = os.environ.get("DECLAN_HA_URL", "").strip().rstrip("/")
    token = os.environ.get("DECLAN_HA_TOKEN", "").strip()
    try:
        parsed = urlsplit(url)
        if (not token or parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            return None
        visitor_entity = configuration.get("DECLAN_VISITORS_ENTITY", VISITORS_PRESENT_ENTITY)
        if not re.fullmatch(r"input_boolean\.[a-z0-9_]+", visitor_entity):
            return None
        request = Request(f"{url}/api/states/{visitor_entity}",
                          headers={"Authorization": f"Bearer {token}"})
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=1) as response:
            state = json.loads(response.read(4096)).get("state")
            return {"on": True, "off": False}.get(state)
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
        and step.get("status") in ("confirmed", "already_set", "skipped", "failed", "unverified", "planned", "requested", "already_requested", "not_requested", "not_configured")
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


HOUSE_STATUS_REQUESTS = {
    "house status", "home status", "what is the status of the house",
    "what's the status of the house", "what is the house status",
    "what's the house status", "give me a house status",
    "give me the house status", "how is the house",
}


def select_routine(phrase, origin):
    """Resolve routine requests exclusively against Home Assistant scripts."""
    phrase = phrase.removeprefix("run ").removeprefix("the ")
    if not 1 <= len(phrase.split()) <= 20:
        return None
    is_house_status = phrase in HOUSE_STATUS_REQUESTS
    connection = ha_device_connection()
    if connection is None:
        return ("unconfigured_house_status", {}) if is_house_status else None
    scripts, error = script_discovery.discover(connection)
    if error:
        return ("unconfigured_house_status", {}) if is_house_status else None
    candidates = [phrase]
    if is_house_status:
        candidates.extend(("house status", "home health summary"))
    if phrase in GOOD_MORNING_PHRASES:
        candidates.append("good morning")
    if phrase in GOOD_NIGHT_PHRASES:
        candidates.append("good night")
    if phrase.replace("’", "'") in DINNER_PHRASES:
        candidates.extend(("dinner is served", "dinner"))
    if phrase in SEXY_TIME_COMMANDS:
        candidates.append("sexy time")
    movie = parse_movie_request(phrase)
    if movie:
        direction, room, app = movie
        candidates.extend((f"{direction} movie time",))
        candidates.append("movie time")
        if room:
            candidates.insert(1, f"{direction} movie time {room}")
    for candidate in dict.fromkeys(candidates):
        found = script_discovery.match(candidate, scripts)
        if found:
            kind, item = found
            if kind == "ambiguous":
                return "auto_ambiguous", {}
            # Generic Movie Time is valid for start/end only if HA declares
            # an operation/action field that can distinguish the direction.
            if movie and movie[0] != "toggle" and candidate == "movie time":
                if not set(item.get("fields", [])) & {"operation", "movie_action", "action", "requested_action"}:
                    continue
            if (SEXY_TIME_COMMANDS.get(phrase) == "end" and candidate == "sexy time"
                    and not set(item.get("fields", [])) & {"operation", "requested_action"}):
                continue
            parameters = {}
            if movie:
                parameters = {"operation": movie[0], "movie_action": movie[0],
                              "action": movie[0], "room": movie[1] or "lounge",
                              "movie_room": movie[1] or "lounge"}
                if "requested_action" in item.get("fields", []):
                    parameters["requested_action"] = movie[0]
                parameters["_declan_background"] = True
            elif phrase in GOOD_MORNING_PHRASES or "good morning" in script_discovery.phrases(item):
                parameters = {"_declan_background": True, "_declan_reply_category": "morning"}
            elif phrase in GOOD_NIGHT_PHRASES or "good night" in script_discovery.phrases(item):
                parameters = {"_declan_background": True, "_declan_reply_category": "night"}
            elif phrase in SEXY_TIME_COMMANDS or "sexy time" in script_discovery.phrases(item):
                parameters = {"operation": SEXY_TIME_COMMANDS.get(phrase, "start"),
                              "_declan_background": True, "_declan_reply_category": "sexy"}
                if "requested_action" in item.get("fields", []):
                    parameters["requested_action"] = parameters["operation"]
            if is_house_status:
                parameters["_declan_expect_response"] = True
            if {"dinner", "dinner is served"} & script_discovery.phrases(item):
                parameters["_declan_reply_category"] = "dinner"
            return "auto:" + item["entity_id"], parameters
    if is_house_status:
        return "unconfigured_house_status", {}
    return None


def select_routine_turn(phrase, origin):
    for join in re.finditer(r"(?:,\s*|\s+)(?:and then|and|then) (?=turn |make |set |dim |play )", phrase):
        follow_on = phrase[join.end():]
        if follow_on.startswith("play ") and parse_movie_request(phrase[:join.start()].removeprefix("run ")):
            continue
        if routine := select_routine(phrase[:join.start()], origin):
            return routine, follow_on
    routine = select_routine(phrase, origin)
    return (routine, None) if routine else None



def preview_routine(phrase, origin=None):
    """Read-only preview of a Home Assistant script; never dispatch actions."""
    selection = select_routine_turn(phrase, origin)
    if not selection:
        return "I couldn't find that script in Home Assistant. Nothing has been run.", "unresolved"
    (kind, options), follow_on = selection
    if follow_on:
        return "I cannot preview chained commands yet. Nothing has been run.", "unresolved"
    if kind == "auto_ambiguous":
        return "Several Home Assistant scripts match. Nothing has been run.", "unresolved"
    if kind == "unconfigured_house_status":
        return "I couldn't find a House Status script in Home Assistant. Nothing has been run.", "not_configured"
    if not kind.startswith("auto:"):
        return "I couldn't identify a Home Assistant script. Nothing has been run.", "unresolved"
    script = kind[5:]
    variables = ", ".join(f"{key}={value}" for key, value in options.items())
    detail = f" with {variables}" if variables else ""
    return (f"Preview: I would request Home Assistant script {script}{detail}. "
            "The script's internal actions and final reply cannot be predicted without running it. "
            "Simulated spoken response: Starting the routine. Nothing has been run.", "preview")


def execute_routine_result(selection, action_results, *, approved=False):
    """Typed execution result for local routine selection with optional status."""
    from local_outcome_contracts import routine_execution_result
    period, options = selection
    if period.startswith("auto:"):
        if options.get("_declan_background"):
            return script_discovery.enqueue_result(
                ha_device_connection(), period[5:],
                {key: value for key, value in options.items() if not key.startswith("_declan_")})
        return script_discovery.execute_result(
            ha_device_connection(), {"entity_id": period[5:]},
            parameters={key: value for key, value in options.items() if not key.startswith("_declan_")},
            expect_response=options.get("_declan_expect_response", False),
            action_results=action_results)
    result = (execute_routine(selection, action_results, approved=True)
              if approved else execute_routine(selection, action_results))
    return routine_execution_result(result)


def _routine_legacy_triple(result, status):
    """Preserve legacy routine callers while validating discovered script outcomes."""
    return result.reply, result.outcome.value, status


def execute_routine(selection, action_results, *, approved=False):
    period, options = selection
    if period == "auto_ambiguous":
        return "Several Home Assistant scripts match that name. Please use a more specific name.", "unresolved", None
    if period.startswith("auto:"):
        if options.get("_declan_background"):
            return _routine_legacy_triple(*script_discovery.enqueue_result(ha_device_connection(), period[5:],
                {key: value for key, value in options.items() if not key.startswith("_declan_")}))
        return _routine_legacy_triple(*script_discovery.execute_result(
            ha_device_connection(), {"entity_id": period[5:]},
            parameters={key: value for key, value in options.items() if not key.startswith("_declan_")},
            expect_response=options.get("_declan_expect_response", False), action_results=action_results))
    if period == "unconfigured_house_status":
        return "I could not find a House Status script in Home Assistant.", "not_configured", None
    return "I couldn't find that routine in Home Assistant.", "not_configured", None


def run_custom_routine(name, action_results=None, *, approved=False, parameters=None):
    """Run a legacy mapped HA script; no per-script approval required."""
    try:
        item = routine_registry.load().get(name)
    except (ValueError, OSError, sqlite3.Error):
        return "Routine configuration is unavailable.", "unverified", None
    if not item:
        return "That routine is not configured.", "not_configured", None
    connection = ha_device_connection()
    if connection is None:
        return "Home Assistant is not connected.", "not_configured", None
    url, headers, opener = connection
    if parameters and "room" in parameters:
        areas = read_ha_areas(connection)
        if parameters["room"] not in areas:
            return "I could not match that room to a Home Assistant area.", "unresolved", None
    script = item["script"]
    # Preserve legacy script parameters for existing installations.
    request_id = "declan-" + secrets.token_hex(16)
    payload = {**item["fields"], **(parameters or {}), "request_id": request_id, "routine_id": script}
    request = Request(f"{url}/api/services/script/{script.split('.', 1)[1]}?return_response",
                      data=json.dumps(payload).encode(), headers=headers, method="POST")
    with track_routine(name, script):
        try:
            with opener.open(request, timeout=55) as response:
                result = json.loads(response.read(65536))
        except HTTPError as error:
            code = error.code
            error.close()
            return f"Home Assistant rejected {name} (HTTP {code}).", "failed", None
        except (OSError, ValueError):
            return f"I couldn't verify {name}. Check its Home Assistant trace.", "unverified", None
        value = result.get("service_response") if isinstance(result, dict) else None
        if isinstance(value, dict) and set(value) == {script}:
            value = value[script]
        if not isinstance(value, dict) or value.get("request_id") != request_id or value.get("routine_id") != script:
            return f"{name} was requested, but completion was not verified.", "unverified", None
        status = value.get("outcome")
        if status not in {"started", "success", "partial", "failed", "cancelled"}:
            return f"{name} returned no verified completion outcome.", "unverified", None
        if action_results is not None:
            action_results.extend(routine_action_results(value.get("steps")))
        steps = routine_action_results(value.get("steps"))
        required = [step for step in steps if step.get("required", True)]
        if status == "success" and (not required or not isinstance(value.get("steps"), list) or len(steps) != len(value["steps"]) or any(step["status"] not in {"confirmed", "already_set"} for step in required)):
            return f"{name} was started, but required steps were not verified.", "unverified", None
        outcome = {"started": "started", "success": "reported_success", "partial": "partial", "failed": "failed", "cancelled": "cancelled"}[status]
        return f"{name} {status}.", outcome, None


def chained_outcome(routine, lighting):
    if routine == "started" and lighting == "confirmed":
        return "started"
    if routine == "execution_completed" and lighting == "confirmed":
        return "execution_completed"
    if routine == "reported_success" and lighting == "confirmed":
        return "reported_success"
    if routine in {"reported_success", "execution_completed", "partial"} or lighting in {"confirmed", "partial"}:
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
def run_routine(period, *, action_results=None, movie_action=None, movie_room="lounge", movie_app=None, approved=False):
    """Call the configured Home Assistant routine once and read its result."""
    salutation = "Movie Time." if movie_action else f"Good {period}."
    lock = ROUTINE_LOCKS["movie_bedroom" if movie_action and movie_room == "bedroom" else period]
    connection = ha_device_connection()
    if connection is None:
        return f"{salutation} The Home Assistant connection isn't configured.", "not_configured", None
    url, headers, opener = connection
    movie_prefix = "DECLAN_BEDROOM_MOVIE" if movie_room == "bedroom" else "DECLAN_MOVIE"
    setting = f"{movie_prefix}_SCRIPT" if movie_action else f"DECLAN_GOOD_{period.upper()}_SCRIPT"
    routine_key = ("movie_bedroom" if movie_room == "bedroom" else "movie") if movie_action else period
    try:
        mapped = routine_registry.load().get(routine_key)
    except (OSError, ValueError, sqlite3.Error):
        return f"{salutation} Routine configuration is unavailable.", "not_configured", None
    if not mapped:
        return f"{salutation} Map a Home Assistant script for {routine_key} in Declan Settings.", "not_configured", None
    if mapped["sensitive"] and not approved:
        return f"{salutation} This routine needs explicit confirmation.", "unresolved", None
    script = mapped["script"]
    remote = mapped.get("remote", "").strip() if movie_app else ""
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
        parameters = {**mapped["fields"], "request_id": request_id, "routine_id": script}
        if movie_action:
            parameters["requested_action"] = movie_action
        request = Request(
            f"{url}/api/services/script/{service}?return_response",
            data=json.dumps(parameters).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with track_routine(routine_key, script):
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
                if outcome == "reported_success":
                    sleep(7)
                    status, note = launch_movie_app(connection, remote, movie_app)
                else:
                    status, note = "skipped", detail or "Movie Time was not verified."
                if action_results is not None:
                    action_results.append({
                        "target": movie_app[0], "action": "open_app", "status": status, "entity_id": remote,
                        "detail": f"{note} Remote: {remote}. Command: app:{movie_app[1]}.",
                    })
            return reply, outcome, detail
        return f"{salutation} Home Assistant did not return a correlated completion result.", "unverified", None
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
        adjustment = re.fullmatch(r"(dim|brighten) (?:the )?(.+)", clause)
        if adjustment:
            targets.append((adjustment[2], "darker" if adjustment[1] == "dim" else "brighter"))
            continue
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
    """Compatibility entry point; parsing and correction flow live outside HTTP."""
    return lighting_intents.handle_light_request(
        phrase, parse_light_command=parse_light_command, set_lights=set_lights,
        action_results=action_results, last_lights=last_lights, origin_device=origin_device)


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
def run_sexy_time(operation, connection, *, approved=False):
    if connection is None:
        return "The Home Assistant connection isn't configured.", "not_configured", None
    try:
        sexy_mapping = routine_registry.load().get("sexy_time")
    except (OSError, ValueError, sqlite3.Error):
        sexy_mapping = None
    if not sexy_mapping:
        return "Map the Sexy Time script in Declan Settings.", "not_configured", None
    if sexy_mapping["sensitive"] and not approved:
        return "Sexy Time requires explicit confirmation.", "unresolved", None
    sexy_script = sexy_mapping["script"]
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
        request_id = "declan-" + secrets.token_hex(16)
        request = Request(
            f"{url}/api/services/script/{sexy_script.split('.', 1)[1]}?return_response", headers=headers,
            data=json.dumps({"operation": operation, "music_player": player, "request_id": request_id, "routine_id": sexy_script}).encode(), method="POST",
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
        if isinstance(result, dict) and set(result) == {sexy_script}:
            result = result[sexy_script]
        if (not isinstance(result, dict) or result.get("operation") != operation
                or result.get("request_id") != request_id or result.get("routine_id") != sexy_script):
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
def start_dinner(connection, *, approved=False):
    # Dinner is a non-safety announcement. Never dispatch it during
    # overnight quiet hours, even when explicitly requested.
    if not personality_policy.overnight_announcement_allowed("dinner"):
        return "Dinner announcements are muted between 23:00 and 07:00.", "skipped"
    if connection is None:
        return "The Home Assistant connection isn't configured.", "not_configured"
    try:
        dinner_mapping = routine_registry.load().get("dinner")
    except (OSError, ValueError, sqlite3.Error):
        dinner_mapping = None
    if not dinner_mapping:
        return "Map the Dinner script in Declan Settings.", "not_configured"
    if dinner_mapping["sensitive"] and not approved:
        return "Dinner routine requires explicit confirmation.", "unresolved"
    url, headers, opener = connection
    announcement = choose_line("dinner_announcement", read_guest_mode())
    request = Request(
        f"{url}/api/services/script/turn_on", headers=headers,
        data=json.dumps({
            "entity_id": dinner_mapping["script"], "variables": {"dinner_message": announcement},
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

    if operation.startswith("assign:"):
        names = operation.partition(":")[2].strip()
        if not re.fullmatch(r"[A-Za-z][A-Za-z '\\-]{0,119}", names):
            return "Tell me who is in charge.", "unresolved"
        request("/api/services/input_text/set_value", {"entity_id": GUEST_REGISTER_ENTITY, "value": names})
        if read_state(GUEST_REGISTER_ENTITY) != names:
            return "I couldn't verify the guest register was updated, so Guest Mode was left unchanged.", "unverified"
        request("/api/services/input_boolean/turn_on", {"entity_id": GUEST_MODE_ENTITY})
        if read_state(GUEST_MODE_ENTITY) != "on":
            return "I updated the guest register, but couldn't verify Guest Mode is on.", "partial"
        return f"{names} are in charge. Guest Mode is on.", "confirmed"

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


def approved_area_labels(areas):
    """Expose readable HA area names without replacing them with legacy aliases."""
    labels = {}
    # read_ha_areas includes compatibility aliases (e.g. bedroom for
    # Master Bedroom). Prefer the full HA area name over its alias.
    for name in areas:
        key = music.room_key(name)
        if len(name) > len(labels.get(key, "")):
            labels[key] = name.title()
    labels["everywhere"] = "Everywhere"
    return labels


def read_ha_inventory(connection):
    return ha_inventory.read(connection)


def read_music_inventory(connection):
    return ha_inventory.read(connection, music=True)


def stop_everywhere_result(connection):
    """Return a typed stop-all result with playback diagnostics."""
    return _stop_everywhere_typed_core(connection)


def stop_everywhere_output(connection):
    """Legacy stop-all response for existing callers."""
    typed, status = stop_everywhere_result(connection)
    return typed.reply, typed.outcome.value, status


def _stop_everywhere_typed_core(connection):
    from execution_results import ExecutionResult, Outcome
    """Stop all active approved Music Assistant destinations, including Everywhere."""
    if connection is None:
        return ExecutionResult("", Outcome.NOT_CONFIGURED), "Home Assistant is not configured."
    inventory, error = read_music_inventory(connection)
    if error:
        return ExecutionResult("", error), "Could not discover the approved music players."
    destinations, players = music.music_players(inventory)
    targets = sorted({entity for entity in destinations.values()
                      if entity and players.get(entity, {}).get("state") in music.ACTIVE})
    # A running Everywhere group owns its members: one stop on the group
    # must not dispatch additional stop requests to the same stream.
    group = destinations.get("everywhere")
    if group in targets:
        members = (players[group].get("attributes") or {}).get("group_members") or []
        targets = [entity for entity in targets if entity == group or entity not in members]
    if not targets:
        return ExecutionResult("", Outcome.CONFIRMED), "No approved music players are currently playing."
    failed = []
    for entity in targets:
        try:
            music.request(connection, "/api/services/media_player/media_stop", {"entity_id": entity}, timeout=2)
            if not music.wait_for(connection, entity, lambda row: row.get("state") in music.STOPPED):
                failed.append(entity)
        except HTTPError as exc:
            exc.close()
            failed.append(entity)
        except (OSError, ValueError):
            failed.append(entity)
    if failed:
        return ExecutionResult("", Outcome.PARTIAL if len(failed) < len(targets) else Outcome.UNVERIFIED), (
            "Could not verify Stop for: " + ", ".join(failed))
    return ExecutionResult("", Outcome.CONFIRMED), "Stopped playback on all active approved music players."


def stop_origin_output(connection, satellite, device):
    """Preserve legacy triple response for callers of origin-specific Stop."""
    result, status = stop_origin_result(connection, satellite, device)
    return result.reply, result.outcome.value, status


def stop_origin_result(connection, satellite, device):
    """Typed stop result for playback on the originating device."""
    from execution_results import ExecutionResult, Outcome
    if connection is None or not (satellite or device):
        return ExecutionResult("", Outcome.UNRESOLVED), "Stop needs an identifiable Assist satellite or device."
    inventory, error = read_music_inventory(connection)
    if error:
        return ExecutionResult("", error), "Could not discover the originating satellite's outputs."
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
        return ExecutionResult("", Outcome.UNRESOLVED), "More than one playback output belongs to the originating device."
    if len(direct) == 1:
        target = direct[0]["entity_id"]
        members = (direct[0].get("attributes") or {}).get("group_members") or []
        if len(members) > 1:
            return ExecutionResult("", Outcome.UNRESOLVED), "The device output is grouped; Stop left the shared group alone."
        try:
            music.request(connection, "/api/services/media_player/media_stop", {"entity_id": target}, timeout=2)
            if music.wait_for(connection, target, lambda row: row.get("state") in music.STOPPED):
                if satellite:
                    timers.stop_due(satellite)
                return ExecutionResult("", Outcome.CONFIRMED), f"Stopped {target}."
        except HTTPError as error:
            error.close()
        except (OSError, ValueError, sqlite3.Error):
            pass
        return ExecutionResult("", Outcome.UNVERIFIED), f"Could not verify Stop on {target}."
    area = origin.get("declan_area") if origin else None
    if not isinstance(area, str) or not area.strip():
        return ExecutionResult("", Outcome.UNRESOLVED), "No playback output or area could be resolved for the satellite."
    reply, outcome = music.control(
        ("media_stop", music.room_key(area)), connection,
        lambda _: (inventory, None),
    )
    if outcome == "confirmed" and satellite:
        try:
            timers.stop_due(satellite)
        except (OSError, sqlite3.Error):
            return ExecutionResult("", Outcome.PARTIAL), "Playback stopped, but the local timer alarm could not be acknowledged."
    return ExecutionResult("", outcome), reply


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



def set_switch_as_light(name, desired_state, inventory, connection, *, preview=False, action_results=None):
    """Only switch entities explicitly marked as lights may receive light commands."""
    if desired_state not in {"on", "off"}:
        return None
    eligible = []
    for row in inventory:
        entity = row.get("entity_id", "") if isinstance(row, dict) else ""
        attributes = row.get("attributes", {}) if isinstance(row, dict) else {}
        if not re.fullmatch(r"switch\.[a-z0-9_]+", entity) or not isinstance(attributes, dict):
            continue
        if attributes.get("declan_as_light") is not True:
            continue
        label = str(attributes.get("friendly_name") or entity.split(".", 1)[1].replace("_", " ")).casefold()
        if name.casefold() in {label, entity.casefold(), entity.split(".", 1)[1].replace("_", " ")}:
            eligible.append((entity, row.get("state"), label))
    if not eligible:
        return None
    if len(eligible) != 1:
        return "More than one marked light switch matches. Please use its exact entity ID.", "unresolved"
    entity, previous, label = eligible[0]
    if previous not in {"on", "off"}:
        return f"{label} is unavailable in Home Assistant.", "unavailable"
    if preview:
        return f"Preview: I would turn {desired_state} {label}.", "preview"
    if previous == desired_state:
        return f"{label} is already {desired_state}.", "confirmed"
    url, headers, opener = connection
    request = Request(f"{url}/api/services/switch/turn_{desired_state}", headers=headers,
                      data=json.dumps({"entity_id": entity}).encode(), method="POST")
    try:
        with opener.open(request, timeout=4) as response:
            response.read(4096)
        state_request = Request(f"{url}/api/states/{entity}", headers=headers)
        with opener.open(state_request, timeout=4) as response:
            observed = json.loads(response.read(8192))
        verified = isinstance(observed, dict) and observed.get("state") == desired_state
    except HTTPError as error:
        error.close()
        verified = False
    except (OSError, ValueError):
        verified = False
    if action_results is not None:
        action_results.append({"target": label, "entity_id": entity, "action": "turn_" + desired_state,
                               "status": "confirmed" if verified else "unverified"})
    return (f"{label} is {desired_state}." if verified else f"I couldn't verify {label} is {desired_state}.",
            "confirmed" if verified else "unverified")


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
        if brightness is None and not require_all and len(resolved_targets) == 1:
            switch_result = set_switch_as_light(name, desired_state, inventory, connection, preview=preview, action_results=action_results)
            if switch_result is not None:
                return switch_result
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



def _bounded_ai_plan(message, exposed, settings, usage_sink=None, inventory=None):
    plan = openai_planner.request_plan(message, exposed, model=settings["model"], api_key=ai_credentials.get_key(), usage_sink=usage_sink, inventory=inventory,
        max_cost_micro_usd=ai_settings._money(settings["request_ceiling_usd"], allow_zero=False))
    if len(plan) > settings["max_actions"]:
        raise ValueError("Too many proposed actions")
    return plan


def guarded_openai_fallback(message, *, source, exposed_entities=()):
    """Opt-in fallback after local handlers. Sensitive targets excluded."""
    try:
        settings = ai_settings.read()
    except (OSError, ValueError, sqlite3.Error):
        return "AI settings are unavailable; local commands still work.", "unresolved", []
    if not settings["enabled"] or not ai_intent_gate.is_action_request(message):
        return None
    connection = ha_device_connection()
    if connection is None:
        return "Home Assistant is unavailable.", "unavailable", []
    inventory, error = read_ha_inventory(connection)
    if error or inventory is None:
        return "I couldn't verify Home Assistant devices.", "unavailable", []
    # Only the authenticated HA integration supplies its effective Assist
    # exposure set. Never use all inventory rows as implicit permission.
    if not isinstance(exposed_entities, (list, tuple)) or len(exposed_entities) > 20000:
        return "AI device permissions are unavailable.", "unresolved", []
    permitted = set(exposed_entities)
    if not permitted or len(permitted) != len(exposed_entities) or any(
            not isinstance(item, str) or not re.fullmatch(r"[a-z_]+\.[a-z0-9_]+", item)
            for item in exposed_entities):
        return "AI device permissions are unavailable.", "unresolved", []
    safe = [row for row in inventory if row["entity_id"] in permitted
            and row["entity_id"].split(".", 1)[0] in settings["allowed_domains"]]
    try:
        safe = ai_context.select(safe, message, limit=openai_planner.MAX_CONTEXT)
        limit = ai_settings._money(settings["monthly_budget_usd"], allow_zero=True)
        ceiling = ai_settings._money(settings["request_ceiling_usd"], allow_zero=False)
        usage = {}
        with history.database() as db:
            result = guarded_fallback.run_guarded_result(
                message, safe,
                planner=lambda text, exposed: _bounded_ai_plan(
                    text, exposed, settings, usage_sink=lambda value: usage.update({"value": value}),
                    inventory=safe),
                dispatcher=lambda action: ha_dispatcher.dispatch_result(
                    action, connection,
                    authorised=lambda candidate: candidate.entity_id in {
                        row["entity_id"] for row in safe
                        if row["state"] not in ("unknown", "unavailable")
                    }),
                budget_db=db, monthly_limit_micro_usd=limit,
                request_ceiling_micro_usd=ceiling,
                charge_micro_usd=lambda: ai_pricing.charge(settings["model"], usage.get("value")),
            )
        return result.reply, result.outcome.value, [
            {"entity_id": action.entity_id, "action": action.service,
             "ai_generated": True, "status": action.status.value,
             **({"detail": action.detail} if settings["diagnostics"] else {})}
            for action in result.actions
        ]
    except (ValueError, OSError, sqlite3.Error):
        return "I couldn't safely complete that request using OpenAI.", "unresolved", []


def converse(message, session_id, routine_reply=None, *, lighting_context=None, scope=None, guest_mode=None):
    """Compatibility entry point; caller holds SESSION_LOCK."""
    return session_orchestration.converse(
        message, session_id, routine_reply, lighting_context=lighting_context,
        scope=scope, guest_mode=guest_mode, sessions=SESSIONS,
        idle_seconds=IDLE_SECONDS, name_pattern=NAME_PATTERN,
        chat_commands=CHAT_COMMANDS, unmatched_reply=UNMATCHED_REPLY,
        decorate=add_sass,
    )


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
        # Record useful request outcomes without logging request bodies,
        # tokens, query strings or routine transcripts.
        route = urlsplit(self.path).path
        if status >= 400:
            DECLAN_EVENT_LOG.warning("HTTP %d %s %s", status, self.command, route)
        elif self.command == "POST" and route in {
            "/api/assist", "/api/chat", "/api/settings/music-playlists",
            "/api/settings/media-players", "/api/updates/install"
        }:
            DECLAN_EVENT_LOG.info("HTTP %d POST %s", status, route)
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
        room_labels = approved_area_labels(areas)
        rooms = sorted(room_labels)
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
            "room_labels": room_labels,
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
        # The HA integration uses its Assist bearer token for this one read-only
        # endpoint. Do not extend this exception to management or update routes.
        token = os.environ.get("DECLAN_ASSIST_TOKEN", "")
        supplied = self.headers.get("Authorization", "")
        capabilities_auth = (
            self.path == "/api/capabilities" and len(token) >= 32
            and secrets.compare_digest(supplied.encode(), f"Bearer {token}".encode())
        )
        # Read-only history is accessible to the HA integration using its
        # existing Assist token. All write/export/update routes stay protected.
        history_auth = (
            (urlsplit(self.path).path == "/api/history"
             or urlsplit(self.path).path == "/api/history/recording-links")
            and len(token) >= 32
            and secrets.compare_digest(supplied.encode(), f"Bearer {token}".encode())
        )
        players_auth = (
            self.path in {"/api/settings/media-players", "/api/settings/music-playlists", "/api/settings/ai"}
            and len(token) >= 32
            and secrets.compare_digest(supplied.encode(), f"Bearer {token}".encode())
        )
        voice_review_auth = (
            self.path == "/api/voicepipeline"
            and len(token) >= 32
            and secrets.compare_digest(supplied.encode(), f"Bearer {token}".encode())
        )
        native_settings_auth = (
            self.path in {"/api/native/settings-status", "/api/native/settings-export",
                          "/api/native/settings-recovery", "/api/native/diagnostics", "/api/native/logs", "/api/native/intents", "/api/native/routines", "/api/native/routine-responses"}
            and len(token) >= 32
            and secrets.compare_digest(supplied.encode(), f"Bearer {token}".encode())
        )
        updates_auth = (
            self.path == "/api/updates/status"
            and len(token) >= 32
            and secrets.compare_digest(supplied.encode(), f"Bearer {token}".encode())
        )
        settings_status_auth = (
            self.path == "/api/native/settings-status"
            and len(token) >= 32
            and secrets.compare_digest(supplied.encode(), f"Bearer {token}".encode())
        )
        if not ingress and not native_settings_auth and not settings_status_auth and not capabilities_auth and not history_auth and not players_auth and not voice_review_auth and not updates_auth and self.client_address[0] != "127.0.0.1":
            self.send_json(403, {"error": "Local access only."})
            return
        if not ingress and not native_settings_auth and not history_auth and not players_auth and not voice_review_auth and not updates_auth and (
            self.path.startswith("/api/history")
            or self.path.startswith("/api/settings/") or self.path in {"/api/voice-profiles", "/api/voicepipeline"}
            or self.path in {"/api/diagnostics", "/api/settings/spotify", "/api/updates", "/api/updates/status"}
        ) and self.headers.get("Host") not in {
            f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"
        }:
            self.send_json(403, {"error": "Use the local Declan address."})
            return
        if self.path == "/":
            self.send_json(404, {"error": "Use the native Declan Home Assistant panel."})
        elif self.path == "/logo.png":
            self.send_body(200, Path(__file__).with_name("logo.png").read_bytes(), "image/png")
        elif self.path == "/health":
            self.send_json(200, {"status": "ok"})
        elif self.path == "/api/capabilities":
            self.send_json(200, {
                "api_version": "1.0",
                "server_version": RELEASE_VERSION,
                "capabilities": ["updates", "ha_status"],
            })
        elif self.path == "/api/native/settings-status":
            try:
                _, source = music.spotify_credentials()
                self.send_json(200, {"spotify_configured": source in {"saved", "environment"}, "spotify_source": source})
            except (OSError, ValueError):
                self.send_json(503, {"error": "Spotify configuration status unavailable."})
        elif self.path in {"/api/native/settings-export", "/api/native/settings-recovery"}:
            try:
                document = (configuration.recovery() if self.path.endswith("recovery") else configuration.export())
                self.send_json(200, {"document": document})
            except (OSError, ValueError, sqlite3.Error):
                self.send_json(503, {"error": "Settings document unavailable."})
        elif self.path == "/api/native/routine-responses":
            scripts, error = script_discovery.discover(ha_device_connection(), fresh=True)
            if error:
                self.send_json(200, {"commands": command_responses.catalog(), "routines": [],
                                     "routine_error": "Home Assistant routines unavailable. Try again."})
            else:
                self.send_json(200, {"commands": command_responses.catalog(), "routines": [{"entity_id": row["entity_id"], "name": row["name"]} for row in scripts]})
        elif self.path == "/api/native/routines":
            self.send_json(410, {"error": "Routine mappings are retired. Home Assistant scripts are the source of truth."})
        elif self.path == "/api/native/intents":
            try:
                self.send_json(200, {"intents": history.learned_intents()})
            except (OSError, sqlite3.Error):
                self.send_json(503, {"error": "Learned intentions unavailable."})
        elif self.path == "/api/native/logs":
            self.send_json(200, {"entries": declan_logs.recent()})
        elif self.path == "/api/native/diagnostics":
            try:
                self.send_json(200, {"traces": diagnostics.recent()})
            except (OSError, ValueError, sqlite3.Error):
                self.send_json(503, {"error": "Diagnostics unavailable."})
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
        elif self.path == "/api/settings/ai":
            try:
                with history.database() as db:
                    usage_micro_usd = ai_budget.monthly_reserved(db)
                self.send_json(200, {"settings": ai_settings.read(),
                                     "key_configured": ai_credentials.configured(),
                                     "month_usage_micro_usd": usage_micro_usd})
            except (OSError, sqlite3.Error, ValueError):
                self.send_json(503, {"error": "AI settings unavailable."})
        elif self.path == "/api/settings/media-players":
            self.approved_player_settings()
        elif self.path == "/api/settings/music-playlists":
            try:
                self.send_json(200, spotify_playlists.listing())
            except (OSError, ValueError):
                self.send_json(503, {"error": "Spotify playlists unavailable."})
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
        elif self.path.startswith("/api/history/recording-links?"):
            try:
                params = parse_qs(urlsplit(self.path).query)
                if set(params) != {"ids"} or len(params["ids"]) != 1:
                    raise ValueError("Missing recording identifiers.")
                identifiers = params["ids"][0].split(",")
                links = history.verified_recording_turns(identifiers)
                linked = set(links.values())
                turns = {str(row["id"]): row for row in history.recent(limit=None) if row["id"] in linked}
                self.send_json(200, {"links": links, "turns": turns})
            except ValueError:
                self.send_json(400, {"error": "Invalid recording identifiers."})
            except (OSError, sqlite3.Error):
                self.send_json(503, {"error": "Recording links unavailable."})
        elif self.path == "/api/history" or self.path.startswith("/api/history?"):
            try:
                params = parse_qs(urlsplit(self.path).query)
                before = int(params["before"][0]) if "before" in params else None
                if before is not None and not 0 < before < 2**63:
                    raise ValueError
                turns = history.recent(before, limit=51)
                aliases = history.learned_intents() if before is None else None
                for turn in turns:
                    turn["teachable"] = (turn["source"] in {"assist", "browser_voice", "browser_keyboard", "ha_sentence"}
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
        elif self.path not in {"/api/chat", "/api/settings/spotify", "/api/tts", "/api/stt", "/api/updates", "/api/history/clear", "/api/history/intents", "/api/settings/import", "/api/settings/media-players", "/api/settings/music-playlists", "/api/settings/ai", "/api/voice-profiles", "/api/voicepipeline", "/api/native/spotify-credentials", "/api/native/settings-import", "/api/native/intents", "/api/native/routines", "/api/native/routine-responses"}:
            self.send_json(404, {"error": "Not found."})
            return
        elif not (
            self.path == "/api/voicepipeline"
            and len(os.environ.get("DECLAN_ASSIST_TOKEN", "")) >= 32
            and secrets.compare_digest(
                self.headers.get("Authorization", "").encode(),
                f'Bearer {os.environ.get("DECLAN_ASSIST_TOKEN", "")}'.encode(),
            )
        ) and not (
            self.path == "/api/settings/ai"
            and len(os.environ.get("DECLAN_ASSIST_TOKEN", "")) >= 32
            and secrets.compare_digest(
                self.headers.get("Authorization", "").encode(),
                f'Bearer {os.environ.get("DECLAN_ASSIST_TOKEN", "")}'.encode(),
            )
        ) and not (
            self.path in {"/api/settings/media-players", "/api/settings/music-playlists"}
            and len(os.environ.get("DECLAN_ASSIST_TOKEN", "")) >= 32
            and secrets.compare_digest(
                self.headers.get("Authorization", "").encode(),
                f'Bearer {os.environ.get("DECLAN_ASSIST_TOKEN", "")}'.encode(),
            )
        ) and not (
            self.path == "/api/chat"
            and len(os.environ.get("DECLAN_ASSIST_TOKEN", "")) >= 32
            and secrets.compare_digest(
                self.headers.get("Authorization", "").encode(),
                f'Bearer {os.environ.get("DECLAN_ASSIST_TOKEN", "")}'.encode(),
            )
        ) and not (
            self.path == "/api/stt"
            and len(os.environ.get("DECLAN_ASSIST_TOKEN", "")) >= 32
            and secrets.compare_digest(
                self.headers.get("Authorization", "").encode(),
                f'Bearer {os.environ.get("DECLAN_ASSIST_TOKEN", "")}'.encode(),
            )
        ) and not (
            self.path == "/api/native/spotify-credentials"
            and len(os.environ.get("DECLAN_ASSIST_TOKEN", "")) >= 32
            and secrets.compare_digest(
                self.headers.get("Authorization", "").encode(),
                f'Bearer {os.environ.get("DECLAN_ASSIST_TOKEN", "")}'.encode(),
            )
        ) and not (
            self.path == "/api/native/settings-import"
            and len(os.environ.get("DECLAN_ASSIST_TOKEN", "")) >= 32
            and secrets.compare_digest(
                self.headers.get("Authorization", "").encode(),
                f'Bearer {os.environ.get("DECLAN_ASSIST_TOKEN", "")}'.encode(),
            )
        ) and not (
            self.path in {"/api/native/intents", "/api/native/routines", "/api/native/routine-responses"}
            and len(os.environ.get("DECLAN_ASSIST_TOKEN", "")) >= 32
            and secrets.compare_digest(
                self.headers.get("Authorization", "").encode(),
                f'Bearer {os.environ.get("DECLAN_ASSIST_TOKEN", "")}'.encode(),
            )
        ) and not (
            self.path == "/api/updates"
            and len(os.environ.get("DECLAN_ASSIST_TOKEN", "")) >= 32
            and secrets.compare_digest(
                self.headers.get("Authorization", "").encode(),
                f'Bearer {os.environ.get("DECLAN_ASSIST_TOKEN", "")}'.encode(),
            )
        ) and not self.has_ingress_access() and (
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
            max_size = 131072 if self.path == "/api/native/routine-responses" else 450000 if self.path == "/api/voice-profiles" else 196608 if self.path == "/api/settings/import" else 65536 if self.path in {"/api/assist/history", "/api/assist", "/api/chat"} else 8192
            if not 0 < size <= max_size:
                raise ValueError
            body = json.loads(self.rfile.read(size))
            # The HA Assist token only authorizes pending match resolution, never
            # speaker deletion, clip clearing or correction of historical records.
            if (self.path == "/api/voicepipeline"
                    and not self.has_ingress_access()
                    and self.client_address[0] != "127.0.0.1"
                    and (not isinstance(body, dict)
                         or body.get("operation") not in {"resolve", "audio", "history", "correct"}
                         or (body.get("operation") == "resolve" and body.get("action") not in {"confirm", "assign", "dismiss", "enrol"})
                         or (body.get("operation") == "audio" and set(body) != {"operation", "interaction_id"})
                         or (body.get("operation") == "history" and set(body) != {"operation"})
                         or (body.get("operation") == "correct" and (set(body) != {"operation", "interaction_id", "assigned_to", "expected_resolution_id", "confirm"} or body.get("confirm") is not True)))):
                self.send_json(403, {"error": "This VoicePipeline action requires local access."})
                return
            if self.path == "/api/native/spotify-credentials":
                if not isinstance(body, dict) or set(body) != {"client_id", "client_secret", "confirm"} or body.get("confirm") is not True:
                    self.send_json(400, {"error": "Explicit confirmation and both credentials required."})
                    return
                self.spotify_settings(body)
                return
            if self.path == "/api/settings/ai":
                try:
                    if not isinstance(body, dict):
                        raise ValueError("Invalid AI settings payload")
                    if set(body) == {"api_key"}:
                        ai_credentials.replace_key(body["api_key"])
                        self.send_json(200, {"key_configured": True})
                    elif set(body) == {"settings"}:
                        self.send_json(200, {"settings": ai_settings.save(body["settings"]),
                                             "key_configured": ai_credentials.configured()})
                    else:
                        raise ValueError("Invalid AI settings payload")
                except ValueError as error:
                    self.send_json(400, {"error": str(error)})
                except (OSError, sqlite3.Error):
                    self.send_json(503, {"error": "Could not save AI settings."})
                return
            if self.path == "/api/settings/media-players":
                self.approved_player_settings(body)
                return
            if self.path == "/api/settings/music-playlists":
                try:
                    if isinstance(body, dict) and set(body) == {"category", "operation"} and body.get("operation") == "refresh":
                        credentials, _ = music.spotify_credentials()
                        if not all(credentials):
                            self.send_json(409, {"error": "Configure Spotify credentials before refreshing playlists."})
                            return
                        self.send_json(200, spotify_playlists.start_refresh(
                            body["category"], lambda: build_opener(ProxyHandler({}))))
                    else:
                        self.send_json(200, spotify_playlists.manage(body))
                except ValueError as error:
                    self.send_json(400, {"error": str(error)})
                except OSError:
                    self.send_json(503, {"error": "Spotify playlist storage unavailable."})
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
            if self.path in {"/api/settings/import", "/api/native/settings-import"}:
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
            if self.path == "/api/native/routine-responses":
                try:
                    if not isinstance(body, dict) or set(body) not in ({"entity_id"}, {"entity_id", "profile", "expected"}):
                        raise ValueError("Invalid response change")
                    entity = body.get("entity_id")
                    if isinstance(entity, str) and entity.startswith("command:"):
                        item = command_responses.item(entity)
                        manager = command_responses
                    else:
                        if not isinstance(entity, str) or not routine_responses.ENTITY.fullmatch(entity):
                            raise ValueError("Select a routine or command")
                        scripts, error = script_discovery.discover(ha_device_connection(), fresh=True)
                        if error:
                            self.send_json(503, {"error": "Home Assistant routines unavailable. Try again."})
                            return
                        item = next((row for row in scripts if row['entity_id'] == entity), None)
                        if item is None:
                            raise ValueError("That routine is no longer available. Reload routines.")
                        manager = routine_responses
                    result = (manager.save(item, body['profile'], body['expected'])
                              if 'profile' in body else manager.snapshot(item))
                    self.send_json(200, result)
                except ValueError as error:
                    self.send_json(400, {"error": str(error)})
                except (OSError, sqlite3.Error):
                    self.send_json(503, {"error": "Routine responses unavailable."})
                return
            if self.path == "/api/native/routines":
                self.send_json(410, {"error": "Routine mappings are retired. Manage scripts in Home Assistant."})
                return
            if self.path == "/api/native/intents":
                try:
                    if not isinstance(body, dict):
                        raise ValueError("Invalid intention change.")
                    if set(body) == {"phrase", "target", "previous"}:
                        history.edit_intent(body["phrase"], body["target"], body["previous"])
                    elif set(body) == {"forget", "previous"}:
                        phrase = body["forget"]
                        if not isinstance(phrase, str) or not isinstance(body["previous"], str) or history.learned_intent(phrase) != body["previous"]:
                            raise ValueError("Intention changed. Refresh before forgetting.")
                        history.forget_intent(phrase)
                    elif set(body) == {"recording_id", "target"}:
                        recording_id = voicepipeline.identifier(body["recording_id"])
                        rows = voicepipeline.interactions() + voicepipeline.interactions(history=True)
                        matches = [row for row in rows if row.get("id") == recording_id]
                        transcripts = {row.get("transcript") for row in matches}
                        if len(transcripts) != 1 or not matches or any(
                                row.get("status") in {"dismissed", "rejected", "discarded"} for row in matches):
                            raise ValueError("Refresh and choose a recording with a transcript.")
                        history.teach_phrase(transcripts.pop(), body["target"])
                    elif set(body) == {"turn_id", "target"} and type(body["turn_id"]) is int:
                        history.teach_intent(body["turn_id"], body["target"], UNMATCHED_REPLY)
                    else:
                        raise ValueError("Invalid intention change.")
                    self.send_json(200, {"saved": True})
                except ValueError as error:
                    self.send_json(400, {"error": str(error)})
                except voicepipeline.PipelineError as error:
                    self.send_json(error.status, {"error": str(error)})
                except (OSError, sqlite3.Error):
                    self.send_json(503, {"error": "Intention change unavailable."})
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
            message, session_id = request_validation.message_and_session(body)
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
        source, scope, origin_device, satellite = request_origin.request_context(
            self.path, body,
        )
        routine_reply = outcome = routine_status = None
        action_results = []
        light_result = None
        if source == "assist":
            speaker = body.get("speaker")
            speaker_name = (speaker.get("name") if isinstance(speaker, dict)
                            and type(speaker.get("confidence")) in (int, float)
                            and speaker["confidence"] >= 0.85 and isinstance(speaker.get("name"), str) else None)
            if not CAPTURE_ARBITER.claim(history.normalize_phrase(message), satellite or origin_device,
                                         body.get("capture"), speaker_name):
                self.send_json(200, {"reply": "", "session_id": session_id or secrets.token_urlsafe(24),
                                     "outcome": "duplicate"})
                return
        with SESSION_LOCK:
            last_lights, last_device, last_information = (
                session_context_retrieval.recent_context(
                    SESSIONS.get(session_id), scope,
                    now=monotonic(), idle_seconds=IDLE_SECONDS,
                )
            )
        lighting_context = None
        status_target = None
        information_context = None
        # Resolve self-corrections and learned aliases before command side effects.
        effective_message, phrase = learned_intent_resolution.resolve(
            message, preprocess=preprocess_speech,
            normalize=history.normalize_phrase,
            learned_intent=history.learned_intent, log_error=self.log_error,
        )
        with SESSION_LOCK:
            pending_retry = retry_context.consume_pending_retry(
                SESSIONS.get(session_id), scope, now=monotonic(),
                window_seconds=retry_learning.WINDOW_SECONDS,
            )
        if pending_retry and history.normalize_phrase(message) in retry_learning.CANCEL:
            with SESSION_LOCK:
                reply = retry_cancellation.cancel_retry(
                    message, session_id, scope=scope, source=source,
                    speaker=body.get("speaker"), converse=converse,
                    record=history.record, log_error=self.log_error,
                )
            self.send_json(200, reply)
            return
        opener = build_opener(ProxyHandler({}), NoRedirect())
        # HA owns script permissions. Guest assignment is a separate privileged
        # action and retains its existing voice confirmation protection.
        routine_approved = True
        session_id, confirmed_phrase, confirmation_reply, is_confirmed = (
            sensitive_confirmation_turn.confirmation_turn(
                message, phrase, session_id, source=source,
                satellite=satellite, origin_device=origin_device,
                speaker=body.get("speaker"),
                evaluate=sensitive_confirmation_decision.evaluate,
                confirmation_response=sensitive_confirmation_response.confirmation_response,
                normalize=history.normalize_phrase, guest_commands=GUEST_COMMANDS,
                confirmations=SENSITIVE_CONFIRMATIONS,
                record=history.record, diagnostic_id=diagnostics.current_id,
                log_error=self.log_error,
            )
        )
        if confirmation_reply is not None:
            self.send_json(200, confirmation_reply)
            return
        if is_confirmed:
            phrase = confirmed_phrase
            effective_message = confirmed_phrase
        routine_preview = routine_preview_dispatch.dispatch_preview(
            phrase, origin_device=origin_device, satellite=satellite,
            detect_phrase=routine_preview_detection.routine_preview_phrase,
            preview_routine=preview_routine,
        )
        timer_result = timer_command_dispatch.dispatch_timer(
            phrase, source=source, origin_device=origin_device, satellite=satellite,
            routine_preview=routine_preview,
            registry_factory=command_registry.timer_registry,
            context_factory=command_registry.RequestContext,
            matches=timers.matches, handle=timers.handle, opener=opener,
            guest_mode=read_guest_mode, decorate=add_sass,
        )
        routine_turn = None
        routine_voice_result = None
        early_result = early_command_result.early_command_result(
            routine_preview, timer_result,
        )
        if early_result is not None:
            routine_reply, outcome = early_result
        elif stop_result := stop_command_dispatch.dispatch_stop(
            phrase, source=source, origin_device=origin_device, satellite=satellite,
            registry_factory=command_registry.stop_registry,
            context_factory=command_registry.RequestContext,
            stop_routines=stop_pending_routines,
            stop_everywhere=stop_everywhere_result,
            connection=ha_device_connection,
        ):
            routine_reply, outcome, routine_status = (
                stop_result_response.stop_result_response(stop_result)
            )
        elif (roast_guest_result := roast_guest_dispatch.dispatch_roast_or_guest(
            phrase, roast_target=roast.target,
            respond_to_roast=roast_command_dispatch.respond_to_roast,
            guest_mode=read_guest_mode, visitors_present=read_visitors_present,
            response_guest_mode=personality_policy.response_guest_mode,
            roast_respond=roast.respond,
            assignment_action=guest_assignment_command.assignment_action,
            guest_commands=GUEST_COMMANDS, guest_assignment=guest_assignment,
            connection=ha_device_connection,
        )) is not None:
            routine_reply, outcome = roast_guest_result
        elif routine_dispatch := routine_registry_dispatch.dispatch_routine(
            phrase, source=source, origin_device=origin_device,
            satellite=satellite, action_results=action_results,
            registry_factory=command_registry.routine_registry,
            context_factory=command_registry.RequestContext,
            select=select_routine_turn, execute=execute_routine_result,
        ):
            routine_status = routine_dispatch.routine_status
            routine_turn = routine_dispatch.routine_selection
            (routine_reply, outcome, lighting_context, routine_voice_result) = (
                routine_follow_on_dispatch.execute_follow_on(
                    routine_dispatch, origin_device=origin_device,
                    satellite=satellite, action_results=action_results,
                    scope=scope, execute=routine_follow_on.execute,
                    parse_music=music.parse, play_music=music.play,
                    connection=ha_device_connection,
                    music_inventory=read_music_inventory,
                    handle_lighting=handle_light_request,
                    last_lights=last_lights, chained_outcome=chained_outcome,
                )
            )
        else:
            information_result = information_command_dispatch.dispatch_information(
                phrase, source=source,
                registry_factory=command_registry.information_registry,
                context_factory=command_registry.RequestContext,
                matches=conditions.matches, follow_up=conditions.follow_up,
                handle=conditions.handle, question_context=conditions.question_context,
                opener=opener, last_information=last_information,
                decorate=add_sass, guest_mode=read_guest_mode,
            )
            if information_result:
                routine_reply, outcome, information_context = (
                    information_result_response.information_result_response(
                        information_result,
                    )
                )
            else:
                local = device_command_dispatch.dispatch_device(
                    phrase, source=source, last_device=last_device,
                    origin_device=origin_device, satellite=satellite,
                    registry_factory=command_registry.registry,
                    dependencies_factory=command_registry.Dependencies,
                    context_factory=command_registry.RequestContext,
                    parse_status=device_status.parse, describe_status=device_status.describe,
                    connection=ha_device_connection, inventory=read_ha_inventory,
                    decorate=add_sass, guest_mode_entity=GUEST_MODE_ENTITY,
                    parse_feedback=music.parse_feedback, feedback=music.feedback_result,
                    parse_control=music.parse_control, control=music.control_result,
                    parse_music=music.parse, play=music.play_result,
                    music_inventory=read_music_inventory, areas=read_ha_areas,
                    search_media=search_media,
                )
                if local is not None:
                    routine_reply, outcome, status_target = (
                        device_result_response.device_result_response(local)
                    )
                else:
                    lighting_result = lighting_result_dispatch.dispatch_lighting_result(
                        phrase, source=source, origin_device=origin_device,
                        satellite=satellite,
                        registry_factory=command_registry.lighting_registry,
                        context_factory=command_registry.RequestContext,
                        matches=lighting_intents.matches,
                        parse_light_command=parse_light_command,
                        handle_light_request=handle_light_request,
                        action_results=action_results, last_lights=last_lights,
                        scope=scope,
                        dispatch_lighting=lighting_command_dispatch.dispatch_lighting,
                        confirmed_lighting_context=(
                            lighting_context_finalization.confirmed_lighting_context
                        ),
                    )
                    if lighting_result is not None:
                        routine_reply, outcome, lighting_context = lighting_result
                        light_result = (routine_reply, outcome)
        fallback_result = fallback_orchestration.resolve_fallback(
            effective_message, routine_reply=routine_reply,
            light_result=light_result, body=body,
            authorization=self.headers.get("Authorization", ""),
            bridge_token=os.environ.get("DECLAN_ASSIST_TOKEN", ""),
            source=source, action_results=action_results,
            exposed_entities=fallback_entity_authorization.exposed_entities,
            dispatch_fallback=guarded_fallback_dispatch.dispatch_fallback,
            fallback_handler=guarded_openai_fallback,
        )
        if fallback_result is not None:
            routine_reply, outcome = fallback_result
        chat_kind = effective_message.casefold().strip(" .?!")
        guest_mode, visitor_present, response_guest_mode = (
            response_persona_context.resolve_response_persona(
                read_guest_mode, read_visitors_present, personality_policy,
            )
        )
        if routine_reply is None and CHAT_COMMANDS.get(chat_kind) == "time":
            information_context = ("time", None, None)
        with SESSION_LOCK:
            previous = SESSIONS.get(session_id)
            actions, phrase_suggestion = turn_context_preparation.prepare_turn_context(
                previous, action_results=action_results, light_result=light_result,
                outcome=outcome, scope=scope, message=message, now=monotonic(),
                suggestion_factory=turn_finalization.lighting_phrase_suggestion,
            )
            reply = turn_response_composition.compose_turn_response(
                effective_message, session_id, routine_reply,
                lighting_context=lighting_context, scope=scope,
                response_guest_mode=response_guest_mode, outcome=outcome,
                routine_turn=routine_turn, light_result=light_result,
                phrase=phrase, action_results=action_results,
                guest_mode=guest_mode, visitor_present=visitor_present,
                routine_voice_result=routine_voice_result, routine_status=routine_status,
                converse=converse, compose=turn_response_orchestration.compose,
                apply_outcome_metadata=turn_finalization.apply_outcome_metadata,
                personality=personality_policy, lines=__import__("personality").LINES,
                parse_music=music.parse, parse_music_control=music.parse_control,
                render_routine=routine_responses.render,
                response_category=lighting_intents.response_category,
                parse_light_command=parse_light_command,
                render_failure=command_responses.failure,
                composition=response_composition,
            )
            turn_persistence_dispatch.persist_turn(
                reply, sessions=SESSIONS,
                finalize=turn_persistence_orchestration.finalize_turn,
                message=message, phrase=phrase,
                outcome=outcome, scope=scope, status_target=status_target,
                information_context=information_context,
                light_result=light_result, action_results=action_results,
                actions=actions, unmatched_reply=UNMATCHED_REPLY,
                now=monotonic(), pending_retry=pending_retry,
                effective_message=effective_message,
                similar=retry_learning.similar,
                normalize_phrase=history.normalize_phrase,
                teach_phrase=history.teach_phrase, source=source,
                routine_status=routine_status,
                phrase_suggestion=phrase_suggestion,
                speaker=body.get("speaker"), record=history.record,
                diagnostic_id=diagnostics.current_id,
                log_error=self.log_error, state_module=session_turn_state,
                training_module=retry_training_persistence,
                history_module=conversation_persistence,
            )
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
            print(f"Declan 2.0 is ready at {url}/", flush=True)
            DECLAN_EVENT_LOG.info("Declan backend started and health check passed (port %d)", server.server_port)
            while worker.is_alive():
                worker.join(timeout=0.5)
                if updates.RESTART.is_set():
                    print("Restarting Declan to activate the selected release.", flush=True)
                    DECLAN_EVENT_LOG.info("Restarting Declan to activate selected release")
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
    declan_logs.install()
    main()



