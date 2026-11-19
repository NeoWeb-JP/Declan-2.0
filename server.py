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
import ha_inventory
import ha_area_switch_actions
import household_routine_dispatch
import ha_speech_transport
import music_stop_dispatch
import movie_ha_helpers
import bedroom_routine_dispatch
import media_title_search
import ai_fallback_dispatch
import routine_request_selection
import routine_execution_dispatch
import lighting_execution_dispatch
import ha_household_status
from pathlib import Path
from threading import Thread
from time import monotonic, sleep
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from execution_results import ExecutionResult, Outcome
from arbitration import CaptureArbiter

import conditions
import sensitive_confirmations
import diagnostics
import declan_logs
import configuration
import media_search_agents
import household_entities
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
import turn_session_entry
import turn_preflight_entry
import turn_preview_stage
import turn_direct_dispatch
import turn_routine_stage
import turn_fallback_dispatch
import turn_response_preparation
import turn_atomic_finalization
import turn_response_composition
import history
import post_body_routing
import music
import approved_media_players
import spotify_playlists
import music_playlists_post
import timers
import updates
import post_operational_routing
import media_settings_routes
import get_request_dispatch
import speech_http_routes
import assist_auth_http
import post_payload_validation
import post_origin_auth_http
import post_route_gate_http
import post_request_entry
import post_entry_gates
import http_response_transport
import http_ingress_security
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
from routine_action_evidence import parse_routine_actions
from home_assistant_results import HomeAssistantStatusResult
from routine_selection_results import RoutineSelection, RoutineSelectionKind, RoutineTurnSelection
from lighting_action_evidence import LightingActionEvidence
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
import routine_execution_gates
import routine_cancellation
import session_turn_state
import lighting_intents
import roast
import personality_policy

DECLAN_EVENT_LOG = logging.getLogger("declan.server")
DECLAN_EVENT_LOG.setLevel(logging.INFO)

SESSION_STORE = session_store.DEFAULT_SESSION_STORE
CAPTURE_ARBITER = CaptureArbiter()
SENSITIVE_CONFIRMATIONS = sensitive_confirmations.ConfirmationGate()
ROUTINE_EXECUTION_GATES = routine_execution_gates.RoutineExecutionGates()
ROUTINE_COOLDOWN = routine_cooldown.RoutineCooldown()
ACTIVE_ROUTINE_REGISTRY = active_routine_registry.ActiveRoutineRegistry()

def track_routine(name, script):
    """Compatibility context manager for mapped routine execution."""
    return ACTIVE_ROUTINE_REGISTRY.track(name, script)

def stop_pending_routines():
    """Compatibility API for mapped routine cancellation."""
    return _routine_legacy_triple(*stop_pending_routines_result())


def stop_pending_routines_result():
    return routine_cancellation.stop_pending_routines_result(
        connection_factory=ha_device_connection,
        active_registry=ACTIVE_ROUTINE_REGISTRY,
    )

IDLE_SECONDS = 300
ASSIST_PORT = 52737
RELEASE_VERSION: str | None = updates.configured_release_version()
SEXY_TIME_COMMANDS = {
    **{phrase: "start" for name in ("sexy time", "sixty time", "60 time", "bedroom mood", "romance mode")
       for phrase in (name, f"start {name}", f"activate {name}")},
    **{phrase: "end" for name in ("sexy time", "sixty time", "60 time", "bedroom mood", "romance mode")
       for phrase in (f"end {name}", f"stop {name}")},
}
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
    "what did i say earlier": "recall_earlier", "what have i said": "recall_earlier",
    "forget this conversation": "forget_chat", "forget our conversation": "forget_chat",
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
    return ha_household_status.home_assistant_status_result(
        environ=os.environ, history_store=history, request_factory=Request,
        opener_factory=build_opener, proxy_factory=ProxyHandler,
        redirect_factory=NoRedirect, parse_url=urlsplit,
    )


def configured_guest_mode_entity():
    return ha_household_status.configured_guest_mode_entity(entities=household_entities)


def read_guest_mode():
    return ha_household_status.read_guest_mode(
        environ=os.environ, entities=household_entities,
        request_factory=Request, opener_factory=build_opener,
        proxy_factory=ProxyHandler, redirect_factory=NoRedirect, parse_url=urlsplit,
    )


def read_visitors_present():
    return ha_household_status.read_visitors_present(
        environ=os.environ, config=configuration,
        visitors_entity=VISITORS_PRESENT_ENTITY,
        request_factory=Request, opener_factory=build_opener,
        proxy_factory=ProxyHandler, redirect_factory=NoRedirect, parse_url=urlsplit,
    )


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
    return routine_request_selection.parse_movie_request(
        phrase, rooms=MOVIE_ROOMS, apps=MOVIE_APPS,
    )


HOUSE_STATUS_REQUESTS = routine_request_selection.HOUSE_STATUS_REQUESTS


def select_routine_result(phrase, origin) -> RoutineSelection | None:
    return routine_request_selection.select_routine_result(
        phrase, origin, connect=ha_device_connection,
        discovery_module=script_discovery, movie_parser=parse_movie_request,
        morning_phrases=GOOD_MORNING_PHRASES, night_phrases=GOOD_NIGHT_PHRASES,
        dinner_phrases=DINNER_PHRASES, sexy_commands=SEXY_TIME_COMMANDS,
    )


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
    return routine_execution_dispatch.run_custom_routine_result(
        name, action_results=action_results, approved=approved, parameters=parameters,
        registry=routine_registry, connect=ha_device_connection, areas_reader=read_ha_areas,
        token_hex=secrets.token_hex, request_factory=Request, tracker=track_routine,
        parse_steps=routine_action_results_typed, extend_evidence=extend_action_evidence,
    )


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
    return media_title_search.search_media_result(
        phrase, config=configuration, connect=ha_device_connection,
        agents=media_search_agents, request_factory=Request,
    )


def launch_movie_app_result(connection, remote, app):
    return movie_ha_helpers.launch_movie_app_result(
        connection, remote, app, request_factory=Request,
    )


def discover_movie_entities(connection, room, *, script, remote, needs_remote):
    return movie_ha_helpers.discover_movie_entities(
        connection, room, script=script, remote=remote, needs_remote=needs_remote,
        inventory_reader=read_ha_inventory_result, area_reader=read_ha_areas,
        inventory_module=ha_inventory,
    )


def verify_legacy_lounge_start(connection, script):
    return movie_ha_helpers.verify_legacy_lounge_start(
        connection, script, inventory_reader=read_ha_inventory_result,
        inventory_module=ha_inventory, entities=household_entities,
    )


@diagnostics.timed("ha_routine")
def run_routine_result(period, *, action_results=None, movie_action=None, movie_room="lounge", movie_app=None, approved=False):
    return routine_execution_dispatch.run_routine_result(
        period, action_results=action_results, movie_action=movie_action,
        movie_room=movie_room, movie_app=movie_app, approved=approved,
        gates=ROUTINE_EXECUTION_GATES, connect=ha_device_connection,
        registry=routine_registry, cooldown=ROUTINE_COOLDOWN,
        token_hex=secrets.token_hex, request_factory=Request, tracker=track_routine,
        completion=routine_completion_result, launch_app=launch_movie_app_result,
        evidence_factory=MovieActionEvidence, append_evidence=append_action_evidence,
        sleep_fn=sleep,
    )


def routine_completion_result(result, request_id, routine_id, period, movie_action, action_results):
    return routine_execution_dispatch.routine_completion_result(
        result, request_id, routine_id, period, movie_action, action_results,
        parse_steps=routine_action_results_typed, extend_evidence=extend_action_evidence,
        sass=add_sass,
    )


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
    return ha_speech_transport.ha_device_connection(
        environ=os.environ, redirect_handler=NoRedirect,
        proxy_handler=ProxyHandler, opener_factory=build_opener,
    )


@diagnostics.timed("bedroom_routine")
def run_sexy_time_result(operation, connection, *, approved=False):
    return bedroom_routine_dispatch.run_sexy_time_result(
        operation, connection, approved=approved, registry=routine_registry,
        gates=ROUTINE_EXECUTION_GATES, inventory_reader=read_music_inventory_result,
        inventory_module=ha_inventory, music_provider=music, request_factory=Request,
        token_hex=secrets.token_hex, choose_response=choose_line, guest_mode=read_guest_mode,
    )


@diagnostics.timed("dinner_dispatch")
def start_dinner_result(connection, *, approved=False):
    return household_routine_dispatch.start_dinner_result(
        connection, approved=approved, policy=personality_policy,
        registry=routine_registry, choose_response=choose_line,
        guest_mode=read_guest_mode, request_factory=Request,
    )


def guest_assignment_result(operation, connection):
    return household_routine_dispatch.guest_assignment_result(
        operation, connection, entities=household_entities,
        sass=add_sass, request_factory=Request,
    )


@diagnostics.timed("speech_generation")
def render_web_voice(message):
    return ha_speech_transport.render_web_voice(
        message, connect=ha_device_connection, config=configuration,
        request_factory=Request,
    )


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
    return music_stop_dispatch.stop_everywhere_result(
        connection, inventory_reader=read_music_inventory_result,
        inventory_module=ha_inventory, music_provider=music,
    )


def stop_origin_output(connection, satellite, device):
    """Preserve legacy triple response for callers of origin-specific Stop."""
    result, status = stop_origin_result(connection, satellite, device)
    return result.reply, result.outcome.value, status


def stop_origin_result(connection, satellite, device):
    return music_stop_dispatch.stop_origin_result(
        connection, satellite, device, inventory_reader=read_music_inventory_result,
        inventory_module=ha_inventory, music_provider=music, timer_provider=timers,
    )


def read_ha_areas(connection, origin=None):
    """Compatibility boundary for Home Assistant area discovery."""
    return ha_area_switch_actions.read_ha_areas(
        connection, origin, request_factory=Request,
    )


def set_switch_as_light_result(name, desired_state, inventory, connection, *, preview=False, action_results=None):
    """Compatibility boundary for explicitly marked switch lights."""
    return ha_area_switch_actions.set_switch_as_light_result(
        name, desired_state, inventory, connection,
        preview=preview, action_results=action_results,
        request_factory=Request, append_evidence=append_action_evidence,
        evidence_factory=LightingActionEvidence,
    )


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
    return lighting_execution_dispatch.set_lights_result(
        name, desired_state, brightness=brightness, preview=preview,
        require_all=require_all, relative_step=relative_step,
        action_results=action_results, origin_device=origin_device,
        connect=ha_device_connection, inventory_reader=read_ha_inventory_result,
        inventory_module=ha_inventory, entities=household_entities,
        sass=add_sass, areas_reader=read_ha_areas,
        switch_dispatch=set_switch_as_light_result, intents=lighting_intents,
        evidence_factory=LightingActionEvidence, append_evidence=append_action_evidence,
        clock=monotonic, sleeper=sleep, request_factory=Request,
    )


def _bounded_ai_plan(message, exposed, settings, usage_sink=None, inventory=None):
    plan = openai_planner.request_plan(message, exposed, model=settings["model"], api_key=ai_credentials.get_key(), usage_sink=usage_sink, inventory=inventory,
        max_cost_micro_usd=ai_settings._money(settings["request_ceiling_usd"], allow_zero=False))
    if len(plan) > settings["max_actions"]:
        raise ValueError("Too many proposed actions")
    return plan


def guarded_openai_fallback_result(message, *, source, exposed_entities=()):
    return ai_fallback_dispatch.guarded_openai_fallback_result(
        message, source=source, exposed_entities=exposed_entities,
        settings_reader=ai_settings.read, intent_gate=ai_intent_gate.is_action_request,
        connect=ha_device_connection, inventory_reader=read_ha_inventory_result,
        inventory_module=ha_inventory, context_selector=ai_context.select,
        planner_module=openai_planner, settings_module=ai_settings,
        history_module=history, fallback_runner=guarded_fallback.run_guarded_result,
        dispatcher=ha_dispatcher.dispatch_result, pricing=ai_pricing.charge,
        bounded_plan=_bounded_ai_plan, evidence_factory=FallbackActionEvidence,
        response_factory=guarded_fallback_dispatch.FallbackResponse,
    )


def converse(message, session_id, routine_reply=None, *, lighting_context=None, scope=None, guest_mode=None):
    """Compatibility entry point; caller holds SESSION_STORE.lock."""
    return session_orchestration.converse(
        message, session_id, routine_reply, lighting_context=lighting_context,
        scope=scope, guest_mode=guest_mode, sessions=SESSION_STORE.sessions,
        idle_seconds=IDLE_SECONDS, name_pattern=NAME_PATTERN,
        chat_commands=CHAT_COMMANDS, unmatched_reply=UNMATCHED_REPLY,
        decorate=add_sass, recall=SESSION_STORE.chat_recall,
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
        http_ingress_security.send_security_headers(self)
        super().end_headers()

    def send_body(self, status, data, content_type, filename=None):
        return http_response_transport.send_body(
            self, status, data, content_type, filename=filename, logger=DECLAN_EVENT_LOG,
        )

    def send_json(self, status, data):
        return http_response_transport.send_json(
            self, status, data, logger=DECLAN_EVENT_LOG,
        )

    def spotify_settings(self, body=None):
        return media_settings_routes.spotify_settings(self, body, music=music)

    def has_ingress_access(self):
        return http_ingress_security.has_ingress_access(self)

    def approved_player_settings(self, body=None):
        return media_settings_routes.approved_player_settings(
            self, body, ha_device_connection=ha_device_connection,
            ha_inventory=ha_inventory,
            read_music_inventory_result=read_music_inventory_result,
            read_ha_areas=read_ha_areas, approved_area_labels=approved_area_labels,
            approved_media_players=approved_media_players,
        )

    def do_GET(self):
        return get_request_dispatch.dispatch(
            self, assist_token=os.environ.get("DECLAN_ASSIST_TOKEN", ""),
            ingress=self.has_ingress_access(),
            logo_path=Path(__file__).with_name("logo.png"),
            health_readiness=health_readiness,
            ha_status=home_assistant_status_result,
            release_version=RELEASE_VERSION, music=music,
            configuration=configuration, script_discovery=script_discovery,
            ha_connection=ha_device_connection, command_responses=command_responses,
            history=history, logs=declan_logs, diagnostics=diagnostics,
            updates=updates, voicepipeline=voicepipeline,
            voice_profiles=voice_profiles, ai_budget=ai_budget,
            ai_settings=ai_settings, ai_credentials=ai_credentials,
            spotify_playlists=spotify_playlists,
        )

    def transcribe_browser_audio(self):
        return speech_http_routes.transcribe_browser_audio(
            self, web_stt=web_stt, connection_factory=ha_device_connection,
            transcribe=traced_transcribe_result,
            token=os.environ.get("DECLAN_HA_TOKEN", "").strip(),
            pipeline=configuration.get("DECLAN_WEB_ASSIST_PIPELINE", "").strip(),
            logger=DECLAN_EVENT_LOG,
        )

    def do_POST(self):
        return post_request_entry.dispatch(self, handle_post=self.handle_post)

    def handle_post(self):
        if not post_entry_gates.enforce(
            self, assist_token=os.environ.get("DECLAN_ASSIST_TOKEN", ""),
            ingress=self.has_ingress_access(),
            authenticate_assist=assist_auth_http.authenticate_assist,
            enforce_known_route=post_route_gate_http.enforce_known_route,
            enforce_origin=post_origin_auth_http.enforce_access,
            transcribe=self.transcribe_browser_audio,
        ):
            return
        try:
            # Assist-token callers may review or resolve pending matches, but not
            # perform destructive VoicePipeline management operations.
            authorized, body = post_payload_validation.read_authorized_body(
                self, ingress=self.has_ingress_access(),
            )
            if not authorized:
                return
            if post_body_routing.dispatch(
                self, body, spotify_save=self.spotify_settings,
                ai_replace_key=ai_credentials.replace_key,
                ai_save=ai_settings.save, ai_configured=ai_credentials.configured,
                music=music, spotify_playlists=spotify_playlists,
                playlist_handler=music_playlists_post.handle_music_playlists,
                opener_factory=lambda: build_opener(ProxyHandler({})),
                voice_manage=voicepipeline.manage,
                pipeline_error=voicepipeline.PipelineError,
                profiles_manage=voice_profiles.manage,
                preview=configuration.preview, apply=configuration.apply,
                command_responses=command_responses,
                routine_responses=routine_responses,
                discover=script_discovery.discover_result,
                connection=ha_device_connection, history=history,
                voicepipeline=voicepipeline, unmatched_reply=UNMATCHED_REPLY,
                forget_intent=history.forget_intent,
                edit_intent=history.edit_intent,
                teach_intent=history.teach_intent,
                storage_errors=(OSError, sqlite3.Error),
            ):
                return
            if post_operational_routing.dispatch_before_validation(
                self, body, updates=updates, release_version=RELEASE_VERSION,
            ):
                return
            message, session_id = post_payload_validation.message_and_session(body)
        except (ValueError, TypeError, KeyError, AttributeError):
            post_payload_validation.send_validation_error(self)
            return
        if post_operational_routing.dispatch_after_validation(
            self, body, message=message, session_id=session_id,
            render=render_web_voice, record=history.record,
            token_urlsafe=secrets.token_urlsafe,
            action_results=routine_action_results_typed,
        ):
            return
        turn = turn_session_entry.prepare(
            self, body, message=message, session_id=session_id,
            arbiter=CAPTURE_ARBITER, normalize=history.normalize_phrase,
            new_session_id=secrets.token_urlsafe, session_store=SESSION_STORE,
            now=monotonic(), idle_seconds=IDLE_SECONDS,
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
        preflight = turn_preflight_entry.resolve(
            self, body, message=message, session_id=session_id,
            scope=scope, source=source, satellite=satellite,
            origin_device=origin_device, session_store=SESSION_STORE,
            now=monotonic(),
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
                GUEST_MODE_ENTITY=configured_guest_mode_entity(),
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
            sessions=SESSION_STORE.sessions, session_lock=SESSION_STORE.lock, clock=monotonic,
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
                if updates.RUNTIME.restart.is_set():
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



