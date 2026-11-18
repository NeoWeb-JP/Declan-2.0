"""Local Declan 2.0 chat prototype. Run with python server.py."""
import argparse
import ipaddress
import json
import logging
import os
import re
import secrets
import sqlite3
from http.server import BaseHTTPRequestHandler
from declan_ingress.http_server import BoundedHTTPServer as ThreadingHTTPServer
from declan_ingress.security import response_headers, secure_page
import ha_inventory
from pathlib import Path
from collections import OrderedDict as OrderedDict  # Re-export for existing test fixtures.
from threading import Lock, Thread
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from execution_results import ExecutionResult, Outcome, MovieLaunchResult, MovieLaunchStatus
from arbitration import CaptureArbiter

import conditions
import sensitive_confirmations
import diagnostics
import declan_logs
import configuration
import health_readiness
import voice_profiles
import voicepipeline
import device_status
import retry_learning
import retry_training_persistence
import conversation_persistence
import turn_finalization
import turn_response_orchestration
import turn_persistence_orchestration
import request_validation
import session_context_retrieval
import retry_context
import retry_cancellation
import sensitive_confirmation_response
import sensitive_confirmation_decision
import sensitive_confirmation_turn
import routine_preview_detection
import routine_preview_dispatch
import guest_assignment_command
import roast_command_dispatch
import timer_command_dispatch
import lighting_command_dispatch
import lighting_context_finalization
import fallback_entity_authorization
import guarded_fallback_dispatch
import turn_context_preparation
import turn_initialization
import turn_preflight
import turn_preview_stage
import turn_direct_dispatch
import turn_routine_stage
import turn_fallback_dispatch
import turn_response_preparation
import turn_atomic_finalization
import turn_response_composition
import history
import training_history_post
import settings_voice_post
import music
import approved_media_players
import spotify_playlists
import music_playlists_post
import timers
import updates
import operational_post_dispatch
import media_settings_routes
import native_read_routes
import operational_read_routes
import settings_read_routes
import history_read_routes
import system_read_routes
import get_access_gate_http
import speech_http_routes
import assist_auth_http
import voicepipeline_access_http
import post_payload_http
import post_origin_auth_http
import post_route_gate_http
import post_request_preflight
import post_content_type_http
import post_validation_errors_http
import sensitive_confirmation_resolution
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
from routine_action_evidence import RoutineActionStatus, parse_routine_actions
from script_provider_results import ScriptProviderResult, ScriptReportedOutcome
from home_assistant_results import HomeAssistantStatus, HomeAssistantStatusResult
from routine_selection_results import RoutineSelection, RoutineSelectionKind, RoutineTurnSelection
from lighting_action_evidence import LightingActionEvidence, LightingActionStatus, LightingActionReason
from movie_action_evidence import MovieActionEvidence
from action_evidence_buffer import ActionEvidenceBuffer, append_action_evidence, extend_action_evidence
from fallback_action_evidence import FallbackActionEvidence
import script_discovery
from intent_preprocessing import preprocess_speech
from personality import add_sass, choose_line
import routine_responses
import routine_follow_on
import response_composition
import command_responses
import command_registry
import session_orchestration
import session_store
import routine_cooldown
import active_routine_registry
import session_turn_state
import lighting_intents
import roast
import personality_policy

DECLAN_EVENT_LOG = logging.getLogger("declan.server")
DECLAN_EVENT_LOG.setLevel(logging.INFO)

SESSION_STORE = session_store.DEFAULT_SESSION_STORE
SESSIONS = SESSION_STORE.sessions  # Compatibility for existing orchestration callers.
SESSION_LOCK = SESSION_STORE.lock
CAPTURE_ARBITER = CaptureArbiter()
SENSITIVE_CONFIRMATIONS = sensitive_confirmations.ConfirmationGate()
ROUTINE_LOCKS = {name: Lock() for name in ("morning", "night", "movie")}
ROUTINE_LOCKS["movie_bedroom"] = Lock()
ROUTINE_COOLDOWN = routine_cooldown.RoutineCooldown()
ACTIVE_ROUTINE_REGISTRY = active_routine_registry.ActiveRoutineRegistry()

def track_routine(name, script):
    """Compatibility context manager for mapped routine execution."""
    return ACTIVE_ROUTINE_REGISTRY.track(name, script)

def stop_pending_routines():
    """Compatibility API for mapped routine cancellation."""
    return _routine_legacy_triple(*stop_pending_routines_result())


def stop_pending_routines_result():
    connection = ha_device_connection()
    if connection is None:
        return ExecutionResult("Home Assistant is not connected.", Outcome.NOT_CONFIGURED), None
    active = ACTIVE_ROUTINE_REGISTRY.snapshot()
    if not active:
        return ExecutionResult("No mapped routine is currently awaiting completion.", Outcome.CONFIRMED), None
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
    return ExecutionResult(message, Outcome.UNVERIFIED if unknown or stopped else Outcome.CONFIRMED), None

IDLE_SECONDS = 300
ASSIST_PORT = 52737
RELEASE_VERSION: str | None = updates.configured_release_version()
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
    """Compatibility API returning the original connection status string."""
    return home_assistant_status_result().status.value


def home_assistant_status_result() -> HomeAssistantStatusResult:
    url = os.environ.get("DECLAN_HA_URL", "").strip().rstrip("/")
    token = os.environ.get("DECLAN_HA_TOKEN", "").strip()
    if not url or not token:
        try:
            if history.has_recent_assist():
                return HomeAssistantStatusResult(HomeAssistantStatus.ASSIST_RECENT)
        except (OSError, sqlite3.Error):
            pass
        return HomeAssistantStatusResult(HomeAssistantStatus.NOT_CONFIGURED)
    try:
        parsed = urlsplit(url)
        if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            return HomeAssistantStatusResult(HomeAssistantStatus.NOT_CONFIGURED)
        request = Request(url + "/api/", headers={"Authorization": f"Bearer {token}"})
        opener = build_opener(ProxyHandler({}), NoRedirect())
        with opener.open(request, timeout=3) as response:
            payload = json.loads(response.read(4096))
            if response.status == 200 and payload == {"message": "API running."}:
                return HomeAssistantStatusResult(HomeAssistantStatus.CONNECTED)
    except HTTPError as error:
        status = error.code
        error.close()
        if status in {401, 403}:
            return HomeAssistantStatusResult(HomeAssistantStatus.AUTHENTICATION_FAILED)
    except (OSError, ValueError):
        pass
    return HomeAssistantStatusResult(HomeAssistantStatus.DISCONNECTED)


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
    """Compatibility API retaining bounded plain-string evidence mappings."""
    return [step.to_wire() for step in routine_action_results_typed(steps)]


def routine_action_results_typed(steps):
    """Read validated typed evidence from the mapped routine provider."""
    return parse_routine_actions(steps)


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


def select_routine_result(phrase, origin) -> RoutineSelection | None:
    """Resolve routine requests exclusively against Home Assistant scripts."""
    phrase = phrase.removeprefix("run ").removeprefix("the ")
    if not 1 <= len(phrase.split()) <= 20:
        return None
    is_house_status = phrase in HOUSE_STATUS_REQUESTS
    connection = ha_device_connection()
    if connection is None:
        return RoutineSelection(RoutineSelectionKind.HOUSE_STATUS_MISSING) if is_house_status else None
    discovery = script_discovery.discover_result(connection)
    if discovery.error is not None:
        return RoutineSelection(RoutineSelectionKind.HOUSE_STATUS_MISSING) if is_house_status else None
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
        found = script_discovery.match_result(candidate, discovery.scripts)
        if found.status is not script_discovery.ScriptMatchStatus.NO_MATCH:
            if found.status is script_discovery.ScriptMatchStatus.AMBIGUOUS:
                return RoutineSelection(RoutineSelectionKind.AMBIGUOUS)
            item = found.selected
            # Generic Movie Time is valid for start/end only if HA declares
            # an operation/action field that can distinguish the direction.
            if movie and movie[0] != "toggle" and candidate == "movie time":
                if not set(item.get("fields", [])) & {"operation", "movie_action", "action", "requested_action"}:
                    continue
            if (SEXY_TIME_COMMANDS.get(phrase) == "end" and candidate == "sexy time"
                    and not set(item.get("fields", [])) & {"operation", "requested_action"}):
                continue
            parameters: dict = {}
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
            return RoutineSelection(RoutineSelectionKind.SCRIPT, item["entity_id"], parameters)
    if is_house_status:
        return RoutineSelection(RoutineSelectionKind.HOUSE_STATUS_MISSING)
    return None


def select_routine(phrase, origin):
    result = select_routine_result(phrase, origin)
    return RoutineSelection.coerce(result).as_legacy_pair() if result is not None else None


def select_routine_turn_result(phrase, origin) -> RoutineTurnSelection | None:
    for join in re.finditer(r"(?:,\s*|\s+)(?:and then|and|then) (?=turn |make |set |dim |play )", phrase):
        follow_on = phrase[join.end():]
        if follow_on.startswith("play ") and parse_movie_request(phrase[:join.start()].removeprefix("run ")):
            continue
        if routine := select_routine_result(phrase[:join.start()], origin):
            return RoutineTurnSelection(RoutineSelection.coerce(routine), follow_on)
    routine = select_routine_result(phrase, origin)
    return RoutineTurnSelection(RoutineSelection.coerce(routine)) if routine is not None else None


def select_routine_turn(phrase, origin):
    result = select_routine_turn_result(phrase, origin)
    return RoutineTurnSelection.coerce(result).as_legacy_pair() if result is not None else None



def preview_routine_result(phrase, origin=None):
    """Read-only preview of a Home Assistant script; never dispatch actions."""
    selection = select_routine_turn_result(phrase, origin)
    if not selection:
        return ExecutionResult("I couldn't find that script in Home Assistant. Nothing has been run.", Outcome.UNRESOLVED)
    selection = RoutineTurnSelection.coerce(selection)
    routine = selection.routine
    if selection.follow_on:
        return ExecutionResult("I cannot preview chained commands yet. Nothing has been run.", Outcome.UNRESOLVED)
    if routine.kind is RoutineSelectionKind.AMBIGUOUS:
        return ExecutionResult("Several Home Assistant scripts match. Nothing has been run.", Outcome.UNRESOLVED)
    if routine.kind is RoutineSelectionKind.HOUSE_STATUS_MISSING:
        return ExecutionResult("I couldn't find a House Status script in Home Assistant. Nothing has been run.", Outcome.NOT_CONFIGURED)
    if routine.kind is not RoutineSelectionKind.SCRIPT:
        return ExecutionResult("I couldn't identify a Home Assistant script. Nothing has been run.", Outcome.UNRESOLVED)
    script = routine.entity_id
    variables = ", ".join(f"{key}={value}" for key, value in routine.options.items())
    detail = f" with {variables}" if variables else ""
    return ExecutionResult(f"Preview: I would request Home Assistant script {script}{detail}. "
            "The script's internal actions and final reply cannot be predicted without running it. "
            "Simulated spoken response: Starting the routine. Nothing has been run.", Outcome.PREVIEW)


def execute_routine_result(selection, action_results, *, approved=False):
    """Typed execution result for local routine selection with optional status."""
    selection = RoutineSelection.coerce(selection)
    options = selection.options
    if selection.kind is RoutineSelectionKind.SCRIPT:
        if options.get("_declan_background"):
            return script_discovery.enqueue_result(
                ha_device_connection(), selection.entity_id,
                {key: value for key, value in options.items() if not key.startswith("_declan_")})
        return script_discovery.execute_result(
            ha_device_connection(), {"entity_id": selection.entity_id},
            parameters={key: value for key, value in options.items() if not key.startswith("_declan_")},
            expect_response=options.get("_declan_expect_response", False),
            action_results=action_results)
    if selection.kind is RoutineSelectionKind.AMBIGUOUS:
        return ExecutionResult("Several Home Assistant scripts match that name. Please use a more specific name.", Outcome.UNRESOLVED), None
    if selection.kind is RoutineSelectionKind.HOUSE_STATUS_MISSING:
        return ExecutionResult("I could not find a House Status script in Home Assistant.", Outcome.NOT_CONFIGURED), None
    return ExecutionResult("I couldn't find that routine in Home Assistant.", Outcome.NOT_CONFIGURED), None


def _routine_legacy_triple(result, status):
    """Preserve legacy routine callers while validating discovered script outcomes."""
    return result.reply, result.outcome.value, status


def execute_routine(selection, action_results, *, approved=False):
    return _routine_legacy_triple(*execute_routine_result(selection, action_results, approved=approved))


def run_custom_routine_result(name, action_results=None, *, approved=False, parameters=None):
    """Run a legacy mapped HA script; no per-script approval required."""
    try:
        item = routine_registry.load().get(name)
    except (ValueError, OSError, sqlite3.Error):
        return ExecutionResult("Routine configuration is unavailable.", Outcome.UNVERIFIED), None
    if not item:
        return ExecutionResult("That routine is not configured.", Outcome.NOT_CONFIGURED), None
    connection = ha_device_connection()
    if connection is None:
        return ExecutionResult("Home Assistant is not connected.", Outcome.NOT_CONFIGURED), None
    url, headers, opener = connection
    if parameters and "room" in parameters:
        areas = read_ha_areas(connection)
        if parameters["room"] not in areas:
            return ExecutionResult("I could not match that room to a Home Assistant area.", Outcome.UNRESOLVED), None
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
            return ExecutionResult(f"Home Assistant rejected {name} (HTTP {code}).", Outcome.FAILED), None
        except (OSError, ValueError):
            return ExecutionResult(f"I couldn't verify {name}. Check its Home Assistant trace.", Outcome.UNVERIFIED), None
        value = result.get("service_response") if isinstance(result, dict) else None
        if isinstance(value, dict) and set(value) == {script}:
            value = value[script]
        if not isinstance(value, dict) or value.get("request_id") != request_id or value.get("routine_id") != script:
            return ExecutionResult(f"{name} was requested, but completion was not verified.", Outcome.UNVERIFIED), None
        provider_result = ScriptProviderResult.parse(value.get("outcome"))
        status = provider_result.outcome
        if status not in {ScriptReportedOutcome.STARTED, ScriptReportedOutcome.SUCCESS,
                          ScriptReportedOutcome.PARTIAL, ScriptReportedOutcome.FAILED, ScriptReportedOutcome.CANCELLED}:
            return ExecutionResult(f"{name} returned no verified completion outcome.", Outcome.UNVERIFIED), None
        steps = routine_action_results_typed(value.get("steps"))
        if action_results is not None:
            extend_action_evidence(action_results, steps)
        required = [step for step in steps if step.required is not False]
        if status is ScriptReportedOutcome.SUCCESS and (not required or not isinstance(value.get("steps"), list) or len(steps) != len(value["steps"]) or any(not step.completed for step in required)):
            return ExecutionResult(f"{name} was started, but required steps were not verified.", Outcome.UNVERIFIED), None
        return ExecutionResult(f"{name} {status}.", provider_result.execution_outcome), None


def chained_outcome(routine, lighting):
    """Compatibility API for plain outcome strings."""
    return chained_outcome_result(routine, lighting).value


def chained_outcome_result(routine, lighting):
    routine, lighting = Outcome(routine), Outcome(lighting)
    if routine in {Outcome.STARTED, Outcome.EXECUTION_COMPLETED, Outcome.REPORTED_SUCCESS} and lighting is Outcome.CONFIRMED:
        return routine
    if routine in {Outcome.REPORTED_SUCCESS, Outcome.EXECUTION_COMPLETED, Outcome.PARTIAL} or lighting in {Outcome.CONFIRMED, Outcome.PARTIAL}:
        return Outcome.PARTIAL
    if Outcome.UNVERIFIED in (routine, lighting):
        return Outcome.UNVERIFIED
    return routine if routine is lighting else Outcome.FAILED


def search_media(phrase):
    """Compatibility API retaining plain reply/outcome pairs."""
    result = search_media_result(phrase)
    return result.as_legacy_pair() if result is not None else None


def search_media_result(phrase):
    match = re.fullmatch(
        r"(?:where can i (?:watch|stream|find)|(?:search|look) for|find (?:the )?(?:movie|film|show)|"
        r"start (?:movie time|cinema time|cinema mode) and play(?: the (?:movie|film|show))?) (.+)",
        phrase,
    )
    if not match:
        return None
    title = match[1].strip()
    if len(title) > 200 or re.search(r"\b(?:and|then)\s+(?:turn|switch|dim|brighten|set|start|stop|unlock|lock|open|play)\b", title):
        return ExecutionResult("Please ask for the film or show separately from any device commands.", Outcome.UNRESOLVED)
    agent = configuration.get("DECLAN_MEDIA_SEARCH_AGENT", "").strip()
    if agent and not re.fullmatch(r"conversation\.[a-z0-9_]+", agent):
        return ExecutionResult("The Declan Local media search agent isn't configured.", Outcome.NOT_CONFIGURED)
    connection = ha_device_connection()
    if connection is None:
        return ExecutionResult("The Home Assistant connection isn't configured.", Outcome.NOT_CONFIGURED)
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
            return ExecutionResult("I couldn't check Home Assistant for the Declan Local media search agent.", Outcome.UNAVAILABLE)
        candidates = {
            entity for entity in entities if isinstance(entity, str)
            and re.fullmatch(r"conversation\.[a-z0-9_]+", entity)
        }
        if agent and agent not in candidates:
            return ExecutionResult("The configured media search agent isn't available in Declan Local.", Outcome.NOT_CONFIGURED)
        if not agent:
            if not candidates:
                return ExecutionResult("I couldn't find an active Declan Local conversation agent in Home Assistant.", Outcome.NOT_CONFIGURED)
            if len(candidates) > 1:
                return ExecutionResult("I found multiple Declan Local agents. Set DECLAN_MEDIA_SEARCH_AGENT to the one you use for media search.", Outcome.NOT_CONFIGURED)
            agent = candidates.pop()
    try:
        request = Request(f"{url}/api/services/conversation/process?return_response",
                          data=json.dumps({"agent_id": agent, "text": f"where can i watch {title}"}).encode(),
                          headers=headers)
        with opener.open(request, timeout=18) as response:
            payload = json.loads(response.read(1024 * 1024))["service_response"]["response"]
        reply = payload["speech"]["plain"]["speech"]
        if isinstance(reply, str) and reply.strip() and payload.get("response_type") != "error":
            return ExecutionResult(reply.strip(), Outcome.SEARCH_RESULT)
    except HTTPError as error:
        error.close()
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return ExecutionResult("I couldn't get a title search result from Declan Local.", Outcome.UNVERIFIED)


def launch_movie_app_result(connection, remote, app):
    label, command = app
    url, headers, opener = connection
    try:
        with opener.open(Request(f"{url}/api/states/{remote}", headers=headers), timeout=1.5) as response:
            state = json.loads(response.read(65536))["state"]
        if state in ("unknown", "unavailable"):
            return MovieLaunchResult(MovieLaunchStatus.SKIPPED, f"The remote is unavailable. I didn't send the {label} command.")
        request = Request(f"{url}/api/services/remote/send_command", headers=headers,
                          data=json.dumps({"entity_id": remote, "command": ["KEY_HOME", f"app:{command}"],
                                           "delay_secs": 2}).encode())
        with opener.open(request, timeout=6):
            pass
    except HTTPError as error:
        error.close()
        return MovieLaunchResult(MovieLaunchStatus.FAILED, f"Home Assistant rejected the {label} launch request.")
    except (OSError, ValueError, KeyError, TypeError):
        return MovieLaunchResult(MovieLaunchStatus.UNVERIFIED, f"I couldn't confirm whether Home Assistant accepted the {label} launch request.")
    return MovieLaunchResult(MovieLaunchStatus.SENT, f"Home Assistant accepted the command to open {label}.")


def discover_movie_entities(connection, room, *, script, remote, needs_remote):
    inventory_result = ha_inventory.InventoryResult.coerce(read_ha_inventory_result(connection))
    inventory, error = inventory_result.inventory, inventory_result.error
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
    inventory_result = ha_inventory.InventoryResult.coerce(read_ha_inventory_result(connection))
    inventory, error = inventory_result.inventory, inventory_result.error
    if error:
        return "Home Assistant didn't return the lounge device states."
    entities = {row.get("entity_id"): row for row in inventory if isinstance(row, dict)}
    if entities.get(script, {}).get("state") != "off":
        return "Home Assistant hasn't confirmed the Movie Time script is off."
    if entities.get("switch.projector_power_socket", {}).get("state") != "on":
        return "The projector power socket hasn't reported that it's on."
    return None


@diagnostics.timed("ha_routine")
def run_routine_result(period, *, action_results=None, movie_action=None, movie_room="lounge", movie_app=None, approved=False):
    """Call the configured Home Assistant routine once and read its result."""
    salutation = "Movie Time." if movie_action else f"Good {period}."
    lock = ROUTINE_LOCKS["movie_bedroom" if movie_action and movie_room == "bedroom" else period]
    connection = ha_device_connection()
    if connection is None:
        return ExecutionResult(f"{salutation} The Home Assistant connection isn't configured.", Outcome.NOT_CONFIGURED), None
    url, headers, opener = connection
    routine_key = ("movie_bedroom" if movie_room == "bedroom" else "movie") if movie_action else period
    try:
        mapped = routine_registry.load().get(routine_key)
    except (OSError, ValueError, sqlite3.Error):
        return ExecutionResult(f"{salutation} Routine configuration is unavailable.", Outcome.NOT_CONFIGURED), None
    if not mapped:
        return ExecutionResult(f"{salutation} Map a Home Assistant script for {routine_key} in Declan Settings.", Outcome.NOT_CONFIGURED), None
    if mapped["sensitive"] and not approved:
        return ExecutionResult(f"{salutation} This routine needs explicit confirmation.", Outcome.UNRESOLVED), None
    script = mapped["script"]
    remote = mapped.get("remote", "").strip() if movie_app else ""
    if movie_app and not re.fullmatch(r"remote\.[a-z0-9_]+", remote):
        return ExecutionResult(f"I don't have a compatible app remote configured for the {movie_room}.", Outcome.NOT_CONFIGURED), None
    if not re.fullmatch(r"script\.[a-z0-9_]+", script):
        return ExecutionResult(f"{salutation} The routine script isn't configured.", Outcome.NOT_CONFIGURED), None
    if not lock.acquire(blocking=False):
        return ExecutionResult(f"The {period} routine request is already in progress.", Outcome.BUSY), None
    try:
        attempt_key = (period, movie_room, movie_action) if movie_action else period
        if not ROUTINE_COOLDOWN.claim(attempt_key):
            return ExecutionResult(f"I already sent a {period} request. I haven't sent another.", Outcome.DUPLICATE), None
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
                return ExecutionResult(f"{salutation} Home Assistant couldn't accept the configured routine.", Outcome.REJECTED), None
            return ExecutionResult(f"{salutation} I couldn't confirm the routine completed. Check its Home Assistant trace.", Outcome.UNVERIFIED), None
        except (OSError, ValueError):
            return ExecutionResult(f"{salutation} I couldn't confirm the routine completed. Check its Home Assistant trace.", Outcome.UNVERIFIED), None
        result = payload.get("service_response") if isinstance(payload, dict) else None
        if movie_action and isinstance(result, dict) and set(result) == {script}:
            result = result[script]
        if movie_action or (isinstance(result, dict) and "schema_version" in result):
            execution, detail = routine_completion_result(result, request_id, script, period, movie_action, action_results)
            outcome = execution.outcome
            if movie_app:
                if outcome is Outcome.REPORTED_SUCCESS:
                    sleep(7)
                    launch = launch_movie_app_result(connection, remote, movie_app)
                    status, note = launch.status, launch.detail
                else:
                    status, note = MovieLaunchStatus.SKIPPED, detail or "Movie Time was not verified."
                if action_results is not None:
                    evidence = MovieActionEvidence(movie_app[0], status, remote,
                                                   f"{note} Remote: {remote}. Command: app:{movie_app[1]}.")
                    append_action_evidence(action_results, evidence)
            return execution, detail
        return ExecutionResult(f"{salutation} Home Assistant did not return a correlated completion result.", Outcome.UNVERIFIED), None
    finally:
        lock.release()


def routine_completion_result(result, request_id, routine_id, period, movie_action, action_results):
    salutation = "Movie Time." if movie_action else f"Good {period}."
    if (not isinstance(result, dict) or result.get("schema_version") != 1
            or result.get("request_id") != request_id or result.get("routine_id") != routine_id):
        if movie_action:
            detail = "Home Assistant didn't return a Movie Time result that matched this request."
            return ExecutionResult(f"{salutation} {detail}", Outcome.UNVERIFIED), detail
        return ExecutionResult(f"{salutation} I couldn't verify the result of this run.", Outcome.UNVERIFIED), None
    outcome = ScriptProviderResult.parse(result.get("outcome")).outcome
    resolved = result.get("resolved_action")
    if movie_action and outcome in (ScriptReportedOutcome.SUCCESS, ScriptReportedOutcome.PARTIAL):
        expected = ("start", "end") if movie_action == "toggle" else (movie_action,)
        if resolved not in expected:
            return ExecutionResult("Movie Time. I couldn't verify that the result matched the requested direction.", Outcome.UNVERIFIED), None
    raw_steps = result.get("steps")
    steps = routine_action_results_typed(raw_steps)
    if action_results is not None:
        extend_action_evidence(action_results, steps)
    required = [step for step in steps if step.required is not False]
    confirmed = any(step.completed for step in required)
    if outcome is ScriptReportedOutcome.SUCCESS and (not required or len(steps) != len(raw_steps)
                                 or any(not step.completed for step in required)):
        outcome = ScriptReportedOutcome.PARTIAL if confirmed else ScriptReportedOutcome.UNKNOWN
    elif outcome is ScriptReportedOutcome.PARTIAL and not confirmed:
        outcome = ScriptReportedOutcome.UNKNOWN
    elif outcome is ScriptReportedOutcome.FAILED and confirmed:
        outcome = ScriptReportedOutcome.PARTIAL
    if outcome is ScriptReportedOutcome.SUCCESS:
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
        return ExecutionResult(reply, Outcome.REPORTED_SUCCESS), detail
    if outcome is ScriptReportedOutcome.BUSY:
        return ExecutionResult(f"{salutation} The routine is already in progress.", Outcome.BUSY), None
    verified = [step.target.replace("_", " ") for step in required if step.completed]
    failed = [step.target.replace("_", " ") for step in required if step.status is RoutineActionStatus.FAILED]
    incomplete = [step.target.replace("_", " ") for step in required
                  if not step.completed and step.status is not RoutineActionStatus.FAILED]
    details = []
    if verified:
        details.append("Home Assistant confirmed " + ", ".join(verified[:8]) + ".")
    if failed:
        details.append("These steps failed: " + ", ".join(failed[:8]) + ".")
    if incomplete:
        details.append("I couldn't confirm " + ", ".join(incomplete[:8]) + ".")
    detail = " ".join(details) or ("Home Assistant reported a failure." if outcome is ScriptReportedOutcome.FAILED
                                   else "I couldn't confirm the routine completed.")
    reply = f"{salutation} {detail}"
    if movie_action and outcome is ScriptReportedOutcome.PARTIAL and resolved in ("start", "end"):
        intro = "Starting Movie Time." if resolved == "start" else "Ending Movie Time."
        reply = add_sass(intro, f"movie_{resolved}", result.get("guest_mode"))
    final_outcome = (ScriptProviderResult(outcome).execution_outcome
                     if outcome in (ScriptReportedOutcome.PARTIAL, ScriptReportedOutcome.FAILED) else Outcome.UNVERIFIED)
    return ExecutionResult(reply, final_outcome), detail


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


def handle_light_request_result(phrase, *, action_results=None, last_lights=(), origin_device=None):
    """Keep typed lighting outcomes through intent and execution dispatch."""
    return lighting_intents.handle_light_request_result(
        phrase, parse_light_command=parse_light_command, set_lights=set_lights_result,
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
def run_sexy_time_result(operation, connection, *, approved=False):
    if connection is None:
        return ExecutionResult("The Home Assistant connection isn't configured.", Outcome.NOT_CONFIGURED), None
    try:
        sexy_mapping = routine_registry.load().get("sexy_time")
    except (OSError, ValueError, sqlite3.Error):
        sexy_mapping = None
    if not sexy_mapping:
        return ExecutionResult("Map the Sexy Time script in Declan Settings.", Outcome.NOT_CONFIGURED), None
    if sexy_mapping["sensitive"] and not approved:
        return ExecutionResult("Sexy Time requires explicit confirmation.", Outcome.UNRESOLVED), None
    sexy_script = sexy_mapping["script"]
    if not SEXY_TIME_LOCK.acquire(blocking=False):
        return ExecutionResult("I'm still handling the previous Sexy Time request.", Outcome.BUSY), None
    try:
        inventory_result = ha_inventory.InventoryResult.coerce(read_music_inventory_result(connection))
        inventory, inventory_error = inventory_result.inventory, inventory_result.error
        if inventory_error:
            return ExecutionResult("I couldn't discover the bedroom music player.", inventory_error), None
        destinations, _ = music.music_players(inventory)
        player = destinations.get("bedroom")
        if not player:
            return ExecutionResult("I couldn't identify one available bedroom satellite speaker. Check its Home Assistant device and area.", Outcome.UNRESOLVED), None
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
            return ExecutionResult("I couldn't confirm the bedroom routine completed. Check its Home Assistant trace.", Outcome.UNVERIFIED), None
        except (OSError, ValueError):
            return ExecutionResult("I couldn't confirm the bedroom routine completed. Check its Home Assistant trace.", Outcome.UNVERIFIED), None

        result = payload.get("service_response") if isinstance(payload, dict) else None
        if isinstance(result, dict) and set(result) == {sexy_script}:
            result = result[sexy_script]
        if (not isinstance(result, dict) or result.get("operation") != operation
                or result.get("request_id") != request_id or result.get("routine_id") != sexy_script):
            return ExecutionResult("I couldn't verify the bedroom routine's result.", Outcome.UNVERIFIED), None

        lighting_ok = result.get("lighting_ok") is True
        if operation == "end":
            music_result = music.control_result(
                ("media_stop", "bedroom"), connection, lambda _: inventory_result,
            )
            music_ok = music_result.outcome is Outcome.CONFIRMED
            if lighting_ok:
                detail = None if music_ok else "Bedroom lights restored. Bedroom music stop could not be verified."
                return ExecutionResult(choose_line("sexy_time_end", read_guest_mode()), Outcome.CONFIRMED if music_ok else Outcome.PARTIAL), detail
            playback = "The music has stopped." if music_ok else "I couldn't verify that the bedroom music stopped."
            return ExecutionResult(f"I couldn't verify the bedroom lights. {playback}", Outcome.PARTIAL if music_ok else Outcome.UNVERIFIED), None

        if not lighting_ok:
            return ExecutionResult("I couldn't verify the bedroom lights, so I held off on the playlist.", Outcome.UNVERIFIED), None
        volume_ok = True
        try:
            music.request(connection, "/api/services/media_player/volume_set",
                          {"entity_id": player, "volume_level": 0.2})
        except (OSError, ValueError):
            volume_ok = False
        music_result = music.play_result(("bedroom", "sexy time music", "spotify"), connection,
                                    lambda _: inventory_result)
        reply, outcome = music_result.reply, music_result.outcome
        spoken = choose_line("sexy_time_start", read_guest_mode())
        if outcome is Outcome.CONFIRMED and volume_ok:
            return ExecutionResult(spoken, Outcome.CONFIRMED), None
        volume_detail = "" if volume_ok else " Bedroom music volume could not be set."
        return ExecutionResult(spoken, Outcome.PARTIAL), f"Bedroom lights set. {reply}{volume_detail}"
    finally:
        SEXY_TIME_LOCK.release()


@diagnostics.timed("dinner_dispatch")
def start_dinner_result(connection, *, approved=False):
    # Dinner is a non-safety announcement. Never dispatch it during
    # overnight quiet hours, even when explicitly requested.
    if not personality_policy.overnight_announcement_allowed("dinner"):
        return ExecutionResult("Dinner announcements are muted between 23:00 and 07:00.", Outcome.SKIPPED)
    if connection is None:
        return ExecutionResult("The Home Assistant connection isn't configured.", Outcome.NOT_CONFIGURED)
    try:
        dinner_mapping = routine_registry.load().get("dinner")
    except (OSError, ValueError, sqlite3.Error):
        dinner_mapping = None
    if not dinner_mapping:
        return ExecutionResult("Map the Dinner script in Declan Settings.", Outcome.NOT_CONFIGURED)
    if dinner_mapping["sensitive"] and not approved:
        return ExecutionResult("Dinner routine requires explicit confirmation.", Outcome.UNRESOLVED)
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
            return ExecutionResult("Home Assistant rejected the dinner announcement request.", Outcome.UNAVAILABLE)
        return ExecutionResult("I couldn't confirm that Home Assistant accepted the dinner announcement request.", Outcome.UNVERIFIED)
    except OSError:
        return ExecutionResult("I couldn't confirm that Home Assistant accepted the dinner announcement request.", Outcome.UNVERIFIED)
    return ExecutionResult(announcement, Outcome.REQUESTED)


def guest_assignment_result(operation, connection):
    if connection is None:
        return ExecutionResult("I couldn't reach Home Assistant to check Guest Mode or the guest register.", Outcome.UNAVAILABLE)
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
            return ExecutionResult("Tell me who is in charge.", Outcome.UNRESOLVED)
        request("/api/services/input_text/set_value", {"entity_id": GUEST_REGISTER_ENTITY, "value": names})
        if read_state(GUEST_REGISTER_ENTITY) != names:
            return ExecutionResult("I couldn't verify the guest register was updated, so Guest Mode was left unchanged.", Outcome.UNVERIFIED)
        request("/api/services/input_boolean/turn_on", {"entity_id": GUEST_MODE_ENTITY})
        if read_state(GUEST_MODE_ENTITY) != "on":
            return ExecutionResult("I updated the guest register, but couldn't verify Guest Mode is on.", Outcome.PARTIAL)
        return ExecutionResult(f"{names} are in charge. Guest Mode is on.", Outcome.CONFIRMED)

    if operation == "clear":
        request("/api/services/input_text/set_value", {"entity_id": GUEST_REGISTER_ENTITY, "value": ""})
        names = read_state(GUEST_REGISTER_ENTITY)
        # Keep Guest Mode in place until the register is verified empty.
        if names != "":
            return ExecutionResult("I couldn't verify that the guest register was cleared, so I left Guest Mode alone.", Outcome.UNVERIFIED)
        request("/api/services/input_boolean/turn_off", {"entity_id": GUEST_MODE_ENTITY})
        if read_state(GUEST_MODE_ENTITY) != "off":
            return ExecutionResult("I cleared the guest register, but couldn't verify that Guest Mode is off.", Outcome.PARTIAL)
        return ExecutionResult(add_sass("I cleared the guest register and turned off Guest Mode.", "guest_cleared", "off"), Outcome.CONFIRMED)

    mode = read_state(GUEST_MODE_ENTITY)
    names = read_state(GUEST_REGISTER_ENTITY)
    if mode not in {"on", "off"} or names is None:
        return ExecutionResult("I couldn't read Guest Mode or the guest register.", Outcome.UNAVAILABLE)
    if mode == "on":
        if names:
            return ExecutionResult(f"Currently in charge: {names}. Guest Mode is on.", Outcome.CONFIRMED)
        return ExecutionResult("Guest Mode is on, but nobody is listed in the guest register.", Outcome.CONFIRMED)
    if names:
        return ExecutionResult(f"Guest Mode is off, but the guest register still lists {names}.", Outcome.CONFIRMED)
    return ExecutionResult(add_sass("Guest Mode is off. The house is back in your hands.", "guest_inactive", mode), Outcome.CONFIRMED)


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
    return read_ha_inventory_result(connection).as_legacy_pair()


def read_ha_inventory_result(connection) -> ha_inventory.InventoryResult:
    return ha_inventory.read_result(connection)


def read_music_inventory(connection):
    return read_music_inventory_result(connection).as_legacy_pair()


def read_music_inventory_result(connection) -> ha_inventory.InventoryResult:
    return ha_inventory.read_result(connection, music=True)


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
    inventory_result = ha_inventory.InventoryResult.coerce(read_music_inventory_result(connection))
    inventory, error = inventory_result.inventory, inventory_result.error
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
    inventory_result = ha_inventory.InventoryResult.coerce(read_music_inventory_result(connection))
    inventory, error = inventory_result.inventory, inventory_result.error
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
    music_result = music.control_result(
        ("media_stop", music.room_key(area)), connection,
        lambda _: inventory_result,
    )
    if music_result.outcome is Outcome.CONFIRMED and satellite:
        try:
            timers.stop_due(satellite)
        except (OSError, sqlite3.Error):
            return ExecutionResult("", Outcome.PARTIAL), "Playback stopped, but the local timer alarm could not be acknowledged."
    return ExecutionResult("", music_result.outcome), music_result.reply


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



def set_switch_as_light_result(name, desired_state, inventory, connection, *, preview=False, action_results=None):
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
        return ExecutionResult("More than one marked light switch matches. Please use its exact entity ID.", Outcome.UNRESOLVED)
    entity, previous, label = eligible[0]
    if previous not in {"on", "off"}:
        return ExecutionResult(f"{label} is unavailable in Home Assistant.", Outcome.UNAVAILABLE)
    if preview:
        return ExecutionResult(f"Preview: I would turn {desired_state} {label}.", Outcome.PREVIEW)
    if previous == desired_state:
        return ExecutionResult(f"{label} is already {desired_state}.", Outcome.CONFIRMED)
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
        evidence = LightingActionEvidence(label, "turn_" + desired_state,
                                          LightingActionStatus.CONFIRMED if verified else LightingActionStatus.UNVERIFIED,
                                          entity_id=entity)
        append_action_evidence(action_results, evidence)
    return ExecutionResult(f"{label} is {desired_state}." if verified else f"I couldn't verify {label} is {desired_state}.", Outcome.CONFIRMED if verified else Outcome.UNVERIFIED)


def set_lights(name, desired_state, *, brightness=None, preview=False, require_all=False, relative_step=10,
               action_results=None, origin_device=None):
    """Compatibility API for callers expecting plain reply/outcome strings."""
    return set_lights_result(
        name, desired_state, brightness=brightness, preview=preview,
        require_all=require_all, relative_step=relative_step,
        action_results=action_results, origin_device=origin_device,
    ).as_legacy_pair()


def set_lights_result(name, desired_state, *, brightness=None, preview=False, require_all=False, relative_step=10,
               action_results=None, origin_device=None):
    """Resolve Home Assistant lights before dispatch and verify their reported states."""
    connection = ha_device_connection()
    if connection is None:
        return ExecutionResult("The Home Assistant connection isn't configured.", Outcome.NOT_CONFIGURED)
    url, headers, opener = connection
    inventory_result = ha_inventory.InventoryResult.coerce(read_ha_inventory_result(connection))
    inventory, error = inventory_result.inventory, inventory_result.error
    if error:
        return ExecutionResult("I couldn't read the lights from Home Assistant.", error)

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
            return ExecutionResult("Home Assistant didn't report any individual lights to check.", Outcome.UNAVAILABLE)
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
            return ExecutionResult(reply, Outcome.PARTIAL if len(unknown) < len(individual_lights) else Outcome.UNVERIFIED)
        return ExecutionResult(add_sass(reply, "lights_status", guest_mode), Outcome.CONFIRMED)

    areas = None
    room_targets = set()

    def load_area_metadata():
        nonlocal areas
        areas = read_ha_areas(connection, origin_device)
    if origin_device is not None:
        load_area_metadata()
        if not areas:
            return ExecutionResult("Which room do you mean? I couldn't verify the Assist device's area.", Outcome.UNRESOLVED)
        local_members = (lights.keys() & next(iter(areas.values()))) - light_groups
        if not local_members:
            return ExecutionResult("Home Assistant didn't report any individual lights in this room.", Outcome.UNRESOLVED)
        if name == "some lights":
            off = sorted(entity for entity in local_members if lights[entity][1] == "off")
            if not off:
                if any(lights[entity][1] not in ("on", "off") for entity in local_members):
                    return ExecutionResult("I couldn't verify any more lights to turn on in this room.", Outcome.UNVERIFIED)
                return ExecutionResult("All the lights I can see in this room are already on.", Outcome.CONFIRMED)
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
    skipped: list[ExecutionResult] = []
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
                skipped.append(ExecutionResult(f"I couldn't tell where to split {target}. Say 'and' between the light names.", Outcome.UNRESOLVED))
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
            evidence = LightingActionEvidence(target, action_name, status, entity_id=entity, detail=detail)
            append_action_evidence(action_results, evidence)

    selected = {}
    room_off_entities = set()
    conflicts = set()
    for target, matches, direction in resolved_targets:
        if not matches:
            record_action(target, direction, LightingActionStatus.SKIPPED, detail=LightingActionReason.UNRESOLVED)
            skipped.append(ExecutionResult(f"I couldn't find a Home Assistant light called {target}.", Outcome.UNRESOLVED))
            continue
        if len(matches) > 1 and target not in room_targets:
            record_action(target, direction, LightingActionStatus.SKIPPED, detail=LightingActionReason.AMBIGUOUS)
            options = ", ".join(sorted(matches))
            skipped.append(ExecutionResult(f"More than one light matches {target}. Try one of these entity IDs: {options}.", Outcome.UNRESOLVED))
            continue
        for entity in sorted(matches):
            label, state = lights[entity]
            if state not in ("on", "off"):
                record_action(label, direction, LightingActionStatus.SKIPPED, entity=entity, detail=LightingActionReason.UNAVAILABLE)
                skipped.append(ExecutionResult(f"Home Assistant says {label} is unavailable.", Outcome.UNAVAILABLE))
                continue
            relative = direction in ("darker", "brighter")
            if (brightness is not None or relative or direction == "very bright") and entity not in dimmable:
                record_action(label, direction, LightingActionStatus.SKIPPED, entity=entity, detail=LightingActionReason.BRIGHTNESS_UNSUPPORTED)
                skipped.append(ExecutionResult(f"Home Assistant doesn't report brightness control for {label}.", Outcome.UNAVAILABLE))
                continue
            percent = brightness
            goal = direction
            if direction == "very bright":
                percent, goal = 100, "on"
            elif relative:
                level = levels.get(entity)
                if state == "off" or not (isinstance(level, (int, float)) and 0 <= level <= 255):
                    reason = LightingActionReason.ALREADY_OFF if state == "off" else LightingActionReason.BRIGHTNESS_UNKNOWN
                    record_action(label, direction, LightingActionStatus.SKIPPED, entity=entity, detail=reason)
                    skipped.append(ExecutionResult(f"I left {label} alone ({reason}).", Outcome.UNAVAILABLE))
                    continue
                change = -relative_step if direction == "darker" else relative_step
                percent = min(100, max(1, round(level * 100 / 255) + change))
                goal = "on"
            if entity in conflicts:
                continue
            if entity in selected and (selected[entity][2], target_levels[entity]) != (goal, percent):
                del selected[entity]
                conflicts.add(entity)
                record_action(label, direction, LightingActionStatus.SKIPPED, entity=entity, detail=LightingActionReason.CONFLICTING_DIRECTIONS)
                skipped.append(ExecutionResult(f"I heard conflicting settings for {label}. I left it alone.", Outcome.UNRESOLVED))
                continue
            selected[entity] = (label, state, goal)
            target_levels[entity] = percent
            if direction == "off" and target in room_targets and not target.startswith("everything except "):
                room_off_entities.add(entity)

    skipped_details = "".join(f" {result.reply}" for result in skipped)
    if not selected:
        if brightness is None and not require_all and len(resolved_targets) == 1:
            switch_result = set_switch_as_light_result(name, desired_state, inventory, connection, preview=preview, action_results=action_results)
            if switch_result is not None:
                return lighting_intents._lighting_result(switch_result)
        return (ExecutionResult(skipped_details.strip(), skipped[0].outcome) if skipped else
                ExecutionResult("Tell me which lights to switch.", Outcome.UNRESOLVED))
    if preview:
        for entity, (label, _, direction) in selected.items():
            record_action(label, direction, LightingActionStatus.PLANNED, entity=entity)
        groups = {}
        for entity, (label, _, direction) in selected.items():
            groups.setdefault((direction, target_levels[entity]), []).append(label)
        plan = [f"set {', '.join(labels)} to {percent}%" if percent is not None
                else f"turn {direction} {', '.join(labels)}"
                for (direction, percent), labels in groups.items()]
        return ExecutionResult(f"Preview: I would {'; '.join(plan)}.{skipped_details}", Outcome.PREVIEW)
    if require_all and skipped:
        for entity, (label, _, direction) in selected.items():
            record_action(label, direction, LightingActionStatus.SKIPPED, entity=entity, detail=LightingActionReason.INCOMPLETE_CORRECTION)
        return ExecutionResult(f"I left the lights unchanged because I couldn't resolve the full correction.{skipped_details}", Outcome.UNRESOLVED)
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
            record_action(label, direction, LightingActionStatus.ALREADY_SET, entity=entity)
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
                record_action(selected[entity][0], direction, LightingActionStatus.SKIPPED, entity=entity, detail=LightingActionReason.DISPATCH_TIME_LIMIT)
            skipped.append(ExecutionResult(f"I ran out of time before sending the command for {labels}.", Outcome.UNVERIFIED))
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
                record_action(selected[entity][0], direction, LightingActionStatus.FAILED, entity=entity, detail=f"HTTP {error.code}")
            skipped.append(ExecutionResult(f"Home Assistant returned HTTP {error.code} for {labels}.", Outcome.ACTION_ERROR))
            continue
        except OSError:
            for entity in entity_ids:
                record_action(selected[entity][0], direction, LightingActionStatus.UNVERIFIED, entity=entity, detail=LightingActionReason.NO_DISPATCH_RESPONSE)
            skipped.append(ExecutionResult(f"I didn't get a response for {labels}.", Outcome.UNVERIFIED))
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
                        record_action(selected[entity][0], direction, LightingActionStatus.CONFIRMED, entity=entity)
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
        record_action(label, direction, LightingActionStatus.UNVERIFIED, entity=entity, detail=str(state))
        percent = target_levels[entity]
        goal = f"at {percent}%" if percent is not None else direction
        skipped.append(ExecutionResult(f"I couldn't confirm {label} is {goal} ({state}).", Outcome.UNVERIFIED))
    confirmations = [
        f"{', '.join(labels)} {'is' if len(labels) == 1 else 'are'} "
        + (f"at {percent}%." if percent is not None else f"{direction}.")
        for (direction, percent), labels in verified.items() if labels
    ]
    reply = " ".join(confirmations + [result.reply for result in skipped])
    outcome = (Outcome.PARTIAL if confirmations else skipped[0].outcome) if skipped else Outcome.CONFIRMED
    if outcome is Outcome.PARTIAL and room_targets:
        reply = add_sass("I handled part of that. Some lighting changes couldn't be confirmed.",
                         "partial_lighting", guest_mode)
    if outcome is Outcome.CONFIRMED:
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
    return ExecutionResult(reply, outcome)



def _bounded_ai_plan(message, exposed, settings, usage_sink=None, inventory=None):
    plan = openai_planner.request_plan(message, exposed, model=settings["model"], api_key=ai_credentials.get_key(), usage_sink=usage_sink, inventory=inventory,
        max_cost_micro_usd=ai_settings._money(settings["request_ceiling_usd"], allow_zero=False))
    if len(plan) > settings["max_actions"]:
        raise ValueError("Too many proposed actions")
    return plan


def guarded_openai_fallback_result(message, *, source, exposed_entities=()):
    """Opt-in fallback after local handlers. Sensitive targets excluded."""
    try:
        settings = ai_settings.read()
    except (OSError, ValueError, sqlite3.Error):
        return guarded_fallback_dispatch.FallbackResponse(ExecutionResult("AI settings are unavailable; local commands still work.", Outcome.UNRESOLVED))
    if not settings["enabled"] or not ai_intent_gate.is_action_request(message):
        return None
    connection = ha_device_connection()
    if connection is None:
        return guarded_fallback_dispatch.FallbackResponse(ExecutionResult("Home Assistant is unavailable.", Outcome.UNAVAILABLE))
    inventory_result = ha_inventory.InventoryResult.coerce(read_ha_inventory_result(connection))
    inventory, error = inventory_result.inventory, inventory_result.error
    if error or inventory is None:
        return guarded_fallback_dispatch.FallbackResponse(ExecutionResult("I couldn't verify Home Assistant devices.", Outcome.UNAVAILABLE))
    # Only the authenticated HA integration supplies its effective Assist
    # exposure set. Never use all inventory rows as implicit permission.
    if not isinstance(exposed_entities, (list, tuple)) or len(exposed_entities) > 20000:
        return guarded_fallback_dispatch.FallbackResponse(ExecutionResult("AI device permissions are unavailable.", Outcome.UNRESOLVED))
    permitted = set(exposed_entities)
    if not permitted or len(permitted) != len(exposed_entities) or any(
            not isinstance(item, str) or not re.fullmatch(r"[a-z_]+\.[a-z0-9_]+", item)
            for item in exposed_entities):
        return guarded_fallback_dispatch.FallbackResponse(ExecutionResult("AI device permissions are unavailable.", Outcome.UNRESOLVED))
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
        return guarded_fallback_dispatch.FallbackResponse(result, tuple(
            FallbackActionEvidence.from_action(action, include_detail=settings["diagnostics"])
            for action in result.actions
        ))
    except (ValueError, OSError, sqlite3.Error):
        return guarded_fallback_dispatch.FallbackResponse(ExecutionResult("I couldn't safely complete that request using OpenAI.", Outcome.UNRESOLVED))


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
def traced_transcribe_result(*args, **kwargs):
    return web_stt.transcribe_result(*args, **kwargs)


def traced_transcribe(*args, **kwargs):
    """Compatibility API retaining the transcript string and timing stage."""
    return traced_transcribe_result(*args, **kwargs).text

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
            if diagnostics.outcome_result(trace).status is diagnostics.DiagnosticOutcome.UNKNOWN:
                diagnostics.set_outcome(trace, diagnostics.DiagnosticOutcome.FAILED if status >= 400 else diagnostics.DiagnosticOutcome.COMPLETED)
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
            diagnostics.set_outcome(trace, data.get('outcome') or (
                diagnostics.DiagnosticOutcome.FAILED if status >= 400 else diagnostics.DiagnosticOutcome.COMPLETED))
            data = {**data, 'diagnostic_id': trace['id']}
        self.send_body(status, json.dumps(data).encode(), "application/json")

    def spotify_settings(self, body=None):
        return media_settings_routes.spotify_settings(self, body, music=music)

    def has_ingress_access(self):
        token = os.environ.get("DECLAN_INGRESS_TOKEN", "")
        supplied = self.headers.get("X-Declan-Ingress-Token", "")
        return (len(token) >= 32 and token != os.environ.get("DECLAN_ASSIST_TOKEN", "")
                and secrets.compare_digest(supplied.encode(), token.encode()))

    def approved_player_settings(self, body=None):
        return media_settings_routes.approved_player_settings(
            self, body, ha_device_connection=ha_device_connection,
            ha_inventory=ha_inventory,
            read_music_inventory_result=read_music_inventory_result,
            read_ha_areas=read_ha_areas, approved_area_labels=approved_area_labels,
            approved_media_players=approved_media_players,
        )

    def do_GET(self):
        if not get_access_gate_http.enforce_access(
            self, ingress=self.has_ingress_access(),
            token=os.environ.get("DECLAN_ASSIST_TOKEN", ""),
        ):
            return
        if system_read_routes.handles(self.path):
            system_read_routes.dispatch(
                self, logo_path=Path(__file__).with_name("logo.png"),
                health_readiness=health_readiness,
                ha_status=home_assistant_status_result,
                release_version=RELEASE_VERSION,
            )
        elif native_read_routes.handles(self.path):
            native_read_routes.dispatch(
                self, music=music, configuration=configuration,
                script_discovery=script_discovery, ha_connection=ha_device_connection,
                command_responses=command_responses, history=history,
                logs=declan_logs, diagnostics=diagnostics,
            )
        elif operational_read_routes.handles(self.path):
            operational_read_routes.dispatch(
                self, ha_status=home_assistant_status_result,
                release_version=RELEASE_VERSION, updates=updates,
                configuration=configuration,
            )
        elif settings_read_routes.handles(self.path):
            settings_read_routes.dispatch(
                self, voicepipeline=voicepipeline, voice_profiles=voice_profiles,
                diagnostics=diagnostics, history=history, ai_budget=ai_budget,
                ai_settings=ai_settings, ai_credentials=ai_credentials,
                spotify_playlists=spotify_playlists,
            )
        elif history_read_routes.handles(self.path):
            history_read_routes.dispatch(self, history=history)
        else:
            self.send_json(404, {"error": "Not found."})

    def transcribe_browser_audio(self):
        return speech_http_routes.transcribe_browser_audio(
            self, web_stt=web_stt, connection_factory=ha_device_connection,
            transcribe=traced_transcribe_result,
            token=os.environ.get("DECLAN_HA_TOKEN", "").strip(),
            pipeline=configuration.get("DECLAN_WEB_ASSIST_PIPELINE", "").strip(),
            logger=DECLAN_EVENT_LOG,
        )

    def do_POST(self):
        if self.path not in {"/api/chat", "/api/assist", "/api/stt", "/api/tts", "/api/assist/history"}:
            return self.handle_post()
        with diagnostics.request(self.path):
            return self.handle_post()

    def handle_post(self):
        if not post_request_preflight.enforce(
            self, assist_token=os.environ.get("DECLAN_ASSIST_TOKEN", ""),
            ingress=self.has_ingress_access(),
            authenticate_assist=assist_auth_http.authenticate_assist,
            enforce_known_route=post_route_gate_http.enforce_known_route,
            enforce_origin=post_origin_auth_http.enforce_access,
        ):
            return
        if self.path == "/api/stt":
            self.transcribe_browser_audio()
            return
        if not post_content_type_http.enforce_json_content_type(self):
            return
        try:
            body = post_payload_http.read_json_body(self)
            # Assist-token callers may review or resolve pending matches, but not
            # perform destructive VoicePipeline management operations.
            if not voicepipeline_access_http.enforce_access(
                self, body, ingress=self.has_ingress_access(),
            ):
                return
            if settings_voice_post.handles(self.path):
                settings_voice_post.dispatch(
                    self, body, spotify_save=self.spotify_settings,
                    ai_replace_key=ai_credentials.replace_key,
                    ai_save=ai_settings.save,
                    ai_configured=ai_credentials.configured,
                    music=music, spotify_playlists=spotify_playlists,
                    playlist_handler=music_playlists_post.handle_music_playlists,
                    opener_factory=lambda: build_opener(ProxyHandler({})),
                    voice_manage=voicepipeline.manage,
                    pipeline_error=voicepipeline.PipelineError,
                    profiles_manage=voice_profiles.manage,
                    preview=configuration.preview, apply=configuration.apply,
                )
                return
            if training_history_post.handles(self.path):
                training_history_post.dispatch(
                    self, body, command_responses=command_responses,
                    routine_responses=routine_responses,
                    discover=script_discovery.discover_result,
                    connection=ha_device_connection, history=history,
                    voicepipeline=voicepipeline, unmatched_reply=UNMATCHED_REPLY,
                    forget_intent=history.forget_intent,
                    edit_intent=history.edit_intent,
                    teach_intent=history.teach_intent,
                    storage_errors=(OSError, sqlite3.Error),
                )
                return
            if operational_post_dispatch.handles_pre_validation(self.path):
                operational_post_dispatch.dispatch_update(
                    self, body, check=updates.check,
                    status_result=updates.status_result,
                    prerelease_versions=updates.prerelease_versions,
                    queue=updates.queue, release_version=RELEASE_VERSION,
                )
                return
            message, session_id = request_validation.message_and_session(body)
        except (ValueError, TypeError, KeyError, AttributeError):
            post_validation_errors_http.send_validation_error(self)
            return
        if operational_post_dispatch.handles_after_validation(self.path):
            operational_post_dispatch.dispatch_validated(
                self, body, message=message, session_id=session_id,
                render=render_web_voice, record=history.record,
                token_urlsafe=secrets.token_urlsafe,
                action_results=routine_action_results_typed,
            )
            return
        turn = turn_initialization.prepare(
            self, body, message=message, session_id=session_id,
            arbiter=CAPTURE_ARBITER, normalize=history.normalize_phrase,
            new_session_id=secrets.token_urlsafe, sessions=SESSIONS,
            lock=SESSION_LOCK, now=monotonic(), idle_seconds=IDLE_SECONDS,
            retrieve=session_context_retrieval.recent_context,
        )
        if turn is None:
            return
        source, scope, origin_device, satellite = turn.source, turn.scope, turn.origin_device, turn.satellite
        last_lights, last_device, last_information = turn.recent_context
        routine_reply = outcome = routine_status = None
        action_results = ActionEvidenceBuffer()
        light_result = None
        lighting_context = None
        status_target = None
        information_context = None
        preflight = turn_preflight.resolve(
            self, body, message=message, session_id=session_id,
            scope=scope, source=source, satellite=satellite,
            origin_device=origin_device, sessions=SESSIONS,
            lock=SESSION_LOCK, now=monotonic(),
            preprocess=preprocess_speech, normalize=history.normalize_phrase,
            learned_intent=history.learned_intent,
            retry_window=retry_learning.WINDOW_SECONDS,
            consume_retry=retry_context.consume_pending_retry,
            cancel_phrases=retry_learning.CANCEL, converse=converse,
            record=history.record, cancel_retry=retry_cancellation.cancel_retry_result,
            confirm=sensitive_confirmation_turn.confirmation_turn_result,
            evaluate=sensitive_confirmation_decision.evaluate_result,
            confirmation_response=sensitive_confirmation_response.confirmation_response,
            guest_commands=GUEST_COMMANDS, confirmations=SENSITIVE_CONFIRMATIONS,
            diagnostic_id=diagnostics.current_id,
            resolve_confirmation=sensitive_confirmation_resolution.resolved_confirmation,
        )
        if preflight is None:
            return
        session_id, phrase, effective_message = preflight.session_id, preflight.phrase, preflight.effective_message
        pending_retry = preflight.pending_retry
        opener = build_opener(ProxyHandler({}), NoRedirect())
        early_result = turn_preview_stage.resolve(
            phrase, source=source, origin_device=origin_device,
            satellite=satellite, opener=opener,
            preview_dispatch=routine_preview_dispatch.dispatch_preview_result,
            detect_phrase=routine_preview_detection.routine_preview_phrase,
            preview_routine=preview_routine_result,
            timer_dispatch=timer_command_dispatch.dispatch_timer,
            registry_factory=command_registry.timer_registry,
            context_factory=command_registry.RequestContext,
            matches=timers.matches, handle=timers.handle_result,
            guest_mode=read_guest_mode, decorate=add_sass,
        )
        routine_turn = None
        routine_voice_result = None
        if early_result is not None:
            routine_reply, outcome = early_result.reply, early_result.outcome
        elif direct_result := turn_direct_dispatch.dispatch(
            phrase, source=source, origin_device=origin_device,
            satellite=satellite,
            stop_registry=command_registry.stop_registry,
            context_factory=command_registry.RequestContext,
            stop_routines=stop_pending_routines_result,
            stop_everywhere=stop_everywhere_result,
            connection=ha_device_connection,
            roast_target=roast.target,
            respond_to_roast=roast_command_dispatch.respond_to_roast_result,
            guest_mode=read_guest_mode, visitors_present=read_visitors_present,
            response_guest_mode=personality_policy.response_guest_mode,
            roast_respond=roast.respond,
            assignment_action=guest_assignment_command.assignment_action,
            guest_commands=GUEST_COMMANDS,
            guest_assignment=guest_assignment_result,
        ):
            routine_reply, outcome = direct_result.reply, direct_result.outcome
            routine_status = direct_result.routine_status
        elif routine_result := turn_routine_stage.dispatch(
            phrase, source=source, origin_device=origin_device,
            satellite=satellite, action_results=action_results,
            scope=scope, last_lights=last_lights,
            registry_factory=command_registry.routine_registry,
            context_factory=command_registry.RequestContext,
            select=select_routine_turn_result, execute=execute_routine_result,
            follow_on_execute=routine_follow_on.execute_result,
            parse_music=music.parse, play_music=music.play_result,
            connection=ha_device_connection,
            music_inventory=read_music_inventory_result,
            handle_lighting=handle_light_request_result,
            chained_outcome=chained_outcome_result,
        ):
            routine_status = routine_result.routine_status
            routine_turn = routine_result.routine_turn
            routine_reply, outcome = routine_result.reply, routine_result.outcome
            lighting_context = routine_result.lighting_context
            routine_voice_result = routine_result.routine_voice_result
        else:
            fallback_dispatch = turn_fallback_dispatch.dispatch(
                phrase, source, opener, last_information, last_device, origin_device, satellite, action_results, last_lights, scope, lighting_context,
                command_registry=command_registry,
                conditions=conditions,
                add_sass=add_sass,
                read_guest_mode=read_guest_mode,
                device_status=device_status,
                ha_device_connection=ha_device_connection,
                read_ha_inventory_result=read_ha_inventory_result,
                GUEST_MODE_ENTITY=GUEST_MODE_ENTITY,
                music=music,
                read_music_inventory_result=read_music_inventory_result,
                read_ha_areas=read_ha_areas,
                search_media_result=search_media_result,
                lighting_intents=lighting_intents,
                parse_light_command=parse_light_command,
                handle_light_request_result=handle_light_request_result,
                lighting_command_dispatch=lighting_command_dispatch,
                lighting_context_finalization=lighting_context_finalization,
            )
            if fallback_dispatch is not None:
                routine_reply, outcome = fallback_dispatch.reply, fallback_dispatch.outcome
                information_context = fallback_dispatch.information_context
                status_target = fallback_dispatch.status_target
                lighting_context = fallback_dispatch.lighting_context
                light_result = fallback_dispatch.light_result
        response_preparation = turn_response_preparation.prepare(
            effective_message, routine_reply=routine_reply, outcome=outcome,
            light_result=light_result, body=body,
            authorization=self.headers.get("Authorization", ""),
            bridge_token=os.environ.get("DECLAN_ASSIST_TOKEN", ""),
            source=source, action_results=action_results,
            exposed_entities=fallback_entity_authorization.exposed_entities,
            dispatch_fallback=guarded_fallback_dispatch.dispatch_fallback_result,
            fallback_handler=guarded_openai_fallback_result,
            guest_mode_reader=read_guest_mode,
            visitors_reader=read_visitors_present,
            personality_policy=personality_policy,
            chat_commands=CHAT_COMMANDS,
            information_context=information_context,
        )
        routine_reply, outcome = response_preparation.reply, response_preparation.outcome
        guest_mode = response_preparation.guest_mode
        visitor_present = response_preparation.visitor_present
        response_guest_mode = response_preparation.response_guest_mode
        information_context = response_preparation.information_context
        response = turn_atomic_finalization.finalize(
            session_id, action_results, light_result, outcome, scope, message, effective_message, routine_reply, lighting_context, response_guest_mode, routine_turn, phrase, guest_mode, visitor_present, routine_voice_result, routine_status, status_target, information_context, pending_retry, source, body,
            sessions=SESSIONS, session_lock=SESSION_LOCK, clock=monotonic,
            turn_context_preparation=turn_context_preparation,
            turn_finalization=turn_finalization,
            turn_response_composition=turn_response_composition,
            turn_response_orchestration=turn_response_orchestration,
            personality_policy=personality_policy,
            personality_lines=__import__("personality").LINES,
            music=music, routine_responses=routine_responses,
            lighting_intents=lighting_intents, parse_light_command=parse_light_command,
            command_responses=command_responses,
            response_composition=response_composition,
            turn_persistence_orchestration=turn_persistence_orchestration,
            unmatched_reply=UNMATCHED_REPLY, retry_learning=retry_learning,
            history=history, diagnostics=diagnostics,
            session_turn_state=session_turn_state,
            retry_training_persistence=retry_training_persistence,
            conversation_persistence=conversation_persistence,
            log_error=self.log_error, converse=converse,
        )
        self.send_json(200, response.to_wire())


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
    # Assist LAN mode explicitly exposes the server to configured LAN clients;
    # the Assist token is validated above before opening the listener.
    bind_address = "0.0.0.0" if args.assist_lan else "127.0.0.1"  # nosec B104
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
            DECLAN_EVENT_LOG.info("Declan backend started and health check passed (port %d)", server.server_port)
            while worker.is_alive():
                worker.join(timeout=0.5)
                if updates.RESTART.is_set():
                    DECLAN_EVENT_LOG.info("Restarting Declan to activate selected release")
                    raise SystemExit(75)
                try:
                    timers.ring_due(opener)
                except Exception:
                    logging.exception("Timer alarms could not be checked.")
                if monotonic() >= next_music_check:
                    next_music_check = monotonic() + 5
                    try:
                        music.skip_blocked_tracks(ha_device_connection(), read_music_inventory_result)
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
            DECLAN_EVENT_LOG.info("Declan backend stopped by keyboard interrupt")
        finally:
            server.shutdown()
            worker.join()



def run_custom_routine(name, action_results=None, *, approved=False, parameters=None):
    """Compatibility API for mapped routine reply/outcome/status triples."""
    return _routine_legacy_triple(*run_custom_routine_result(
        name, action_results, approved=approved, parameters=parameters))


def run_routine(period, *, action_results=None, movie_action=None, movie_room="lounge", movie_app=None, approved=False):
    """Compatibility API for mapped routine execution."""
    return _routine_legacy_triple(*run_routine_result(
        period, action_results=action_results, movie_action=movie_action,
        movie_room=movie_room, movie_app=movie_app, approved=approved))


def format_routine_result(result, request_id, routine_id, period, movie_action, action_results):
    """Compatibility API for correlated routine completion replies."""
    return _routine_legacy_triple(*routine_completion_result(
        result, request_id, routine_id, period, movie_action, action_results))


def run_sexy_time(operation, connection, *, approved=False):
    """Compatibility API for the mapped bedroom routine."""
    return _routine_legacy_triple(*run_sexy_time_result(operation, connection, approved=approved))


def launch_movie_app(connection, remote, app):
    """Compatibility API for app-launch status and detail strings."""
    return launch_movie_app_result(connection, remote, app).as_legacy_pair()


def start_dinner(connection, *, approved=False):
    """Compatibility API for announcement reply/outcome strings."""
    return start_dinner_result(connection, approved=approved).as_legacy_pair()


def guest_assignment(operation, connection):
    """Compatibility API for guest assignment reply/outcome strings."""
    return guest_assignment_result(operation, connection).as_legacy_pair()


def set_switch_as_light(name, desired_state, inventory, connection, *, preview=False, action_results=None):
    """Compatibility API for marked switch-as-light reply/outcome pairs."""
    result = set_switch_as_light_result(name, desired_state, inventory, connection,
                                      preview=preview, action_results=action_results)
    return result.as_legacy_pair() if result is not None else None


def guarded_openai_fallback(message, *, source, exposed_entities=()):
    """Compatibility API retaining the reply/outcome/action-steps triple."""
    response = guarded_openai_fallback_result(message, source=source, exposed_entities=exposed_entities)
    return response.as_legacy_triple() if response is not None else None


def preview_routine(phrase, origin=None):
    """Compatibility API for read-only preview reply/outcome pairs."""
    return preview_routine_result(phrase, origin).as_legacy_pair()

if __name__ == "__main__":
    declan_logs.install()
    main()



