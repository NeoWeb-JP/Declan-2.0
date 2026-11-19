"""Local Declan 2.0 chat prototype. Run with python server.py."""
import argparse as argparse
import ipaddress
import logging
import os
import re
import secrets
import sqlite3 as sqlite3
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
import server_lifecycle
import routine_turn_orchestration
import light_command_parsing
import post_ingress_orchestration
import turn_dispatch_orchestration
import turn_session_preflight
import turn_response_completion
import sys
from pathlib import Path
from threading import Thread
from time import monotonic, sleep
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from execution_results import ExecutionResult as ExecutionResult, Outcome
from arbitration import CaptureArbiter

import conditions as conditions
import sensitive_confirmations
import diagnostics
import declan_logs
import configuration
import media_search_agents
import household_entities
import health_readiness
import voice_profiles
import voicepipeline
import device_status as device_status
import retry_learning as retry_learning
import retry_training_persistence as retry_training_persistence
import conversation_persistence as conversation_persistence
import turn_finalization as turn_finalization
import turn_response_orchestration as turn_response_orchestration
import turn_persistence_orchestration as turn_persistence_orchestration
import session_context_retrieval as session_context_retrieval
import retry_context as retry_context
import retry_cancellation as retry_cancellation
import sensitive_confirmation_response as sensitive_confirmation_response
import sensitive_confirmation_decision as sensitive_confirmation_decision
import sensitive_confirmation_turn as sensitive_confirmation_turn
import routine_preview_detection as routine_preview_detection
import routine_preview_dispatch as routine_preview_dispatch
import guest_assignment_command as guest_assignment_command
import roast_command_dispatch as roast_command_dispatch
import timer_command_dispatch as timer_command_dispatch
import lighting_command_dispatch as lighting_command_dispatch
import lighting_context_finalization as lighting_context_finalization
import fallback_entity_authorization as fallback_entity_authorization
import guarded_fallback_dispatch
import turn_context_preparation as turn_context_preparation
import turn_session_entry as turn_session_entry
import turn_preflight_entry as turn_preflight_entry
import turn_preview_stage as turn_preview_stage
import turn_direct_dispatch as turn_direct_dispatch
import turn_routine_stage as turn_routine_stage
import turn_fallback_dispatch as turn_fallback_dispatch
import turn_response_preparation as turn_response_preparation
import turn_atomic_finalization as turn_atomic_finalization
import turn_response_composition as turn_response_composition
import history
import post_body_routing as post_body_routing
import music
import approved_media_players
import spotify_playlists
import music_playlists_post as music_playlists_post
import timers
import updates
import post_operational_routing as post_operational_routing
import media_settings_routes
import get_request_dispatch
import speech_http_routes
import assist_auth_http as assist_auth_http
import post_payload_validation as post_payload_validation
import post_origin_auth_http as post_origin_auth_http
import post_route_gate_http as post_route_gate_http
import post_request_entry
import post_entry_gates as post_entry_gates
import http_response_transport
import http_ingress_security
import sensitive_confirmation_resolution as sensitive_confirmation_resolution
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
from home_assistant_results import HomeAssistantStatus as HomeAssistantStatus, HomeAssistantStatusResult
from routine_selection_results import RoutineSelection, RoutineTurnSelection
from lighting_action_evidence import LightingActionEvidence
from movie_action_evidence import MovieActionEvidence
from action_evidence_buffer import ActionEvidenceBuffer, append_action_evidence, extend_action_evidence
from fallback_action_evidence import FallbackActionEvidence
import script_discovery
from intent_preprocessing import preprocess_speech as preprocess_speech
from personality import add_sass, choose_line
import routine_responses as routine_responses
import routine_follow_on as routine_follow_on
import response_composition as response_composition
import command_responses
import command_registry as command_registry
import session_orchestration
import session_store
import routine_cooldown
import active_routine_registry
import routine_execution_gates
import routine_cancellation
import session_turn_state as session_turn_state
import lighting_intents
import roast as roast
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
    return routine_turn_orchestration.select_routine_turn_result(
        phrase, origin, select=select_routine_result, parse_movie=parse_movie_request,
    )


def select_routine_turn(phrase, origin):
    result = select_routine_turn_result(phrase, origin)
    return RoutineTurnSelection.coerce(result).as_legacy_pair() if result is not None else None


def preview_routine_result(phrase, origin=None):
    return routine_turn_orchestration.preview_routine_result(
        phrase, origin, select_turn=select_routine_turn_result,
    )


def execute_routine_result(selection, action_results, *, approved=False):
    return routine_turn_orchestration.execute_routine_result(
        selection, action_results, approved=approved,
        discovery=script_discovery, connect=ha_device_connection,
    )


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
    return light_command_parsing.parse_light_command(phrase)


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
        prepared = post_ingress_orchestration.prepare(self, r=sys.modules[__name__])
        if prepared is None:
            return
        body, message, session_id = prepared
        turn = turn_session_preflight.prepare(
            self, body, message, session_id, r=sys.modules[__name__],
        )
        if turn is None:
            return
        session_id, phrase, effective_message = turn.session_id, turn.phrase, turn.effective_message
        pending_retry = turn.pending_retry
        source, scope, origin_device, satellite = turn.source, turn.scope, turn.origin_device, turn.satellite
        last_lights, last_device, last_information = turn.last_lights, turn.last_device, turn.last_information
        routine_reply = outcome = routine_status = None
        action_results = ActionEvidenceBuffer()
        light_result = lighting_context = status_target = information_context = None
        dispatch_result = turn_dispatch_orchestration.dispatch(
            phrase, source=source, origin_device=origin_device,
            satellite=satellite, action_results=action_results,
            scope=scope, last_lights=last_lights,
            last_device=last_device, last_information=last_information,
            r=sys.modules[__name__],
        )
        routine_reply, outcome = dispatch_result.reply, dispatch_result.outcome
        routine_status, routine_turn = dispatch_result.routine_status, dispatch_result.routine_turn
        routine_voice_result = dispatch_result.routine_voice_result
        lighting_context, information_context = dispatch_result.lighting_context, dispatch_result.information_context
        status_target, light_result = dispatch_result.status_target, dispatch_result.light_result
        response = turn_response_completion.complete(
            self, body=body, message=message, effective_message=effective_message,
            session_id=session_id, phrase=phrase, source=source, scope=scope,
            pending_retry=pending_retry, action_results=action_results,
            dispatch_result=dispatch_result, r=sys.modules[__name__],
        )
        self.send_json(200, response.to_wire())


def main():
    return server_lifecycle.main(
        description=__doc__, argv=None, environ=os.environ,
        history_store=history, timer_store=timers,
        server_factory=ThreadingHTTPServer, handler=Handler,
        thread_factory=Thread, clock=monotonic,
        opener_factory=build_opener, proxy_factory=ProxyHandler,
        logger=DECLAN_EVENT_LOG, updates_module=updates, music_module=music,
        ha_connect=ha_device_connection, music_inventory=read_music_inventory_result,
        ip_address=ipaddress.ip_address, assist_port=ASSIST_PORT,
    )


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



