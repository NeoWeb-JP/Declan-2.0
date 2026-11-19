"""Local Declan 2.0 chat prototype. Run with python server.py."""
import argparse as argparse
import ipaddress
import logging
import os
import secrets
import sqlite3 as sqlite3
from http.server import BaseHTTPRequestHandler
from declan_ingress.http_server import BoundedHTTPServer as ThreadingHTTPServer
import ha_inventory
import ha_area_switch_actions
import household_routine_dispatch as household_routine_dispatch
import ha_speech_transport as ha_speech_transport
import music_stop_dispatch
import movie_ha_helpers
import bedroom_routine_dispatch as bedroom_routine_dispatch
import media_title_search
import ai_fallback_dispatch as ai_fallback_dispatch
import routine_request_selection as routine_request_selection
import routine_execution_dispatch as routine_execution_dispatch
import lighting_execution_dispatch as lighting_execution_dispatch
import ha_household_status as ha_household_status
import server_lifecycle
import routine_turn_orchestration as routine_turn_orchestration
import light_command_parsing
import post_ingress_orchestration as post_ingress_orchestration
import turn_dispatch_orchestration as turn_dispatch_orchestration
import turn_session_preflight as turn_session_preflight
import turn_response_completion as turn_response_completion
import command_vocabulary
import http_handler_adapters
import turn_http_entry
import domain_boundary_helpers
import household_selection_boundaries
import legacy_response_adapters
import runtime_dispatch_boundaries
import sys
from pathlib import Path as Path
from threading import Thread
from time import monotonic, sleep
from urllib.parse import urlsplit as urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from execution_results import ExecutionResult as ExecutionResult, Outcome as Outcome
from arbitration import CaptureArbiter

import conditions as conditions
import sensitive_confirmations
import diagnostics
import declan_logs
import configuration
import media_search_agents
import household_entities
import health_readiness as health_readiness
import voice_profiles as voice_profiles
import voicepipeline as voicepipeline
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
import guarded_fallback_dispatch as guarded_fallback_dispatch
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
import approved_media_players as approved_media_players
import spotify_playlists as spotify_playlists
import music_playlists_post as music_playlists_post
import timers
import updates
import post_operational_routing as post_operational_routing
import media_settings_routes as media_settings_routes
import get_request_dispatch as get_request_dispatch
import speech_http_routes as speech_http_routes
import assist_auth_http as assist_auth_http
import post_payload_validation as post_payload_validation
import post_origin_auth_http as post_origin_auth_http
import post_route_gate_http as post_route_gate_http
import post_request_entry
import post_entry_gates as post_entry_gates
import http_response_transport as http_response_transport
import http_ingress_security
import sensitive_confirmation_resolution as sensitive_confirmation_resolution
import web_stt
import openai_planner
import ai_settings
import ai_credentials
import ai_pricing as ai_pricing
import ai_budget as ai_budget
import ai_context as ai_context
import ai_intent_gate as ai_intent_gate
import guarded_fallback as guarded_fallback
import ha_dispatcher as ha_dispatcher
import routine_registry
from routine_action_evidence import parse_routine_actions
from home_assistant_results import HomeAssistantStatus as HomeAssistantStatus, HomeAssistantStatusResult
from routine_selection_results import RoutineSelection, RoutineTurnSelection
from lighting_action_evidence import LightingActionEvidence
from movie_action_evidence import MovieActionEvidence as MovieActionEvidence
from action_evidence_buffer import ActionEvidenceBuffer as ActionEvidenceBuffer, append_action_evidence, extend_action_evidence
from fallback_action_evidence import FallbackActionEvidence as FallbackActionEvidence
import script_discovery as script_discovery
from intent_preprocessing import preprocess_speech as preprocess_speech
from personality import add_sass, choose_line
import routine_responses as routine_responses
import routine_follow_on as routine_follow_on
import response_composition as response_composition
import command_responses as command_responses
import command_registry as command_registry
import session_orchestration
import session_store
import routine_cooldown
import active_routine_registry
import routine_execution_gates
import routine_cancellation
import session_turn_state as session_turn_state
import lighting_intents as lighting_intents
import roast as roast
import personality_policy as personality_policy

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
SEXY_TIME_COMMANDS = command_vocabulary.SEXY_TIME_COMMANDS
DINNER_PHRASES = command_vocabulary.DINNER_PHRASES
GUEST_MODE_ENTITY = command_vocabulary.GUEST_MODE_ENTITY
GUEST_REGISTER_ENTITY = command_vocabulary.GUEST_REGISTER_ENTITY
VISITORS_PRESENT_ENTITY = command_vocabulary.VISITORS_PRESENT_ENTITY
GUEST_COMMANDS = command_vocabulary.GUEST_COMMANDS
UNMATCHED_REPLY = command_vocabulary.UNMATCHED_REPLY
NAME_PATTERN = command_vocabulary.NAME_PATTERN
CHAT_COMMANDS = command_vocabulary.CHAT_COMMANDS
GOOD_MORNING_SCRIPT = command_vocabulary.GOOD_MORNING_SCRIPT
GOOD_MORNING_PHRASES = command_vocabulary.GOOD_MORNING_PHRASES
GOOD_NIGHT_SCRIPT = command_vocabulary.GOOD_NIGHT_SCRIPT
GOOD_NIGHT_PHRASES = command_vocabulary.GOOD_NIGHT_PHRASES

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def home_assistant_status():
    """Compatibility API returning the original connection status string."""
    return home_assistant_status_result().status.value


def home_assistant_status_result() -> HomeAssistantStatusResult:
    return household_selection_boundaries.home_assistant_status_result(r=sys.modules[__name__])

def configured_guest_mode_entity():
    return household_selection_boundaries.configured_guest_mode_entity(r=sys.modules[__name__])

def read_guest_mode():
    return household_selection_boundaries.read_guest_mode(r=sys.modules[__name__])

def read_visitors_present():
    return household_selection_boundaries.read_visitors_present(r=sys.modules[__name__])

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
    return household_selection_boundaries.parse_movie_request(phrase, r=sys.modules[__name__])

def select_routine_result(phrase, origin) -> RoutineSelection | None:
    return household_selection_boundaries.select_routine_result(phrase, origin, r=sys.modules[__name__])

def select_routine(phrase, origin):
    result = select_routine_result(phrase, origin)
    return RoutineSelection.coerce(result).as_legacy_pair() if result is not None else None


def select_routine_turn_result(phrase, origin) -> RoutineTurnSelection | None:
    return household_selection_boundaries.select_routine_turn_result(phrase, origin, r=sys.modules[__name__])

def select_routine_turn(phrase, origin):
    result = select_routine_turn_result(phrase, origin)
    return RoutineTurnSelection.coerce(result).as_legacy_pair() if result is not None else None


def preview_routine_result(phrase, origin=None):
    return household_selection_boundaries.preview_routine_result(phrase, origin, r=sys.modules[__name__])

def execute_routine_result(selection, action_results, *, approved=False):
    return household_selection_boundaries.execute_routine_result(selection, action_results, approved=approved, r=sys.modules[__name__])

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
    return domain_boundary_helpers.chained_outcome_result(routine, lighting)

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
    return runtime_dispatch_boundaries.run_routine_result(period, action_results=action_results, movie_action=movie_action, movie_room=movie_room, movie_app=movie_app, approved=approved, r=sys.modules[__name__])

def routine_completion_result(result, request_id, routine_id, period, movie_action, action_results):
    return runtime_dispatch_boundaries.routine_completion_result(result, request_id, routine_id, period, movie_action, action_results, r=sys.modules[__name__])

def parse_light_command(phrase):
    return light_command_parsing.parse_light_command(phrase)


@diagnostics.timed("lighting")
def handle_light_request(phrase, *, action_results=None, last_lights=(), origin_device=None):
    return runtime_dispatch_boundaries.handle_light_request(phrase, action_results=action_results, last_lights=last_lights, origin_device=origin_device, r=sys.modules[__name__])

def handle_light_request_result(phrase, *, action_results=None, last_lights=(), origin_device=None):
    return runtime_dispatch_boundaries.handle_light_request_result(phrase, action_results=action_results, last_lights=last_lights, origin_device=origin_device, r=sys.modules[__name__])

def ha_device_connection():
    return ha_speech_transport.ha_device_connection(
        environ=os.environ, redirect_handler=NoRedirect,
        proxy_handler=ProxyHandler, opener_factory=build_opener,
    )


@diagnostics.timed("bedroom_routine")
def run_sexy_time_result(operation, connection, *, approved=False):
    return runtime_dispatch_boundaries.run_sexy_time_result(operation, connection, approved=approved, r=sys.modules[__name__])

@diagnostics.timed("dinner_dispatch")
def start_dinner_result(connection, *, approved=False):
    return runtime_dispatch_boundaries.start_dinner_result(connection, approved=approved, r=sys.modules[__name__])

def guest_assignment_result(operation, connection):
    return runtime_dispatch_boundaries.guest_assignment_result(operation, connection, r=sys.modules[__name__])

@diagnostics.timed("speech_generation")
def render_web_voice(message):
    return runtime_dispatch_boundaries.render_web_voice(message, r=sys.modules[__name__])

def approved_area_labels(areas):
    return domain_boundary_helpers.approved_area_labels(areas, room_key=music.room_key)

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
    return runtime_dispatch_boundaries.set_lights_result(name, desired_state, brightness=brightness, preview=preview, require_all=require_all, relative_step=relative_step, action_results=action_results, origin_device=origin_device, r=sys.modules[__name__])

def _bounded_ai_plan(message, exposed, settings, usage_sink=None, inventory=None):
    return domain_boundary_helpers.bounded_ai_plan(message, exposed, settings, usage_sink=usage_sink, inventory=inventory, planner=openai_planner, credentials=ai_credentials, money=ai_settings._money)

def guarded_openai_fallback_result(message, *, source, exposed_entities=()):
    return runtime_dispatch_boundaries.guarded_openai_fallback_result(message, source=source, exposed_entities=exposed_entities, r=sys.modules[__name__])

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
        return http_handler_adapters.send_body(self, status, data, content_type, filename=filename, r=sys.modules[__name__])

    def send_json(self, status, data):
        return http_handler_adapters.send_json(self, status, data, r=sys.modules[__name__])

    def spotify_settings(self, body=None):
        return http_handler_adapters.spotify_settings(self, body, r=sys.modules[__name__])

    def has_ingress_access(self):
        return http_handler_adapters.has_ingress_access(self, r=sys.modules[__name__])

    def approved_player_settings(self, body=None):
        return http_handler_adapters.approved_player_settings(self, body, r=sys.modules[__name__])

    def do_GET(self):
        return http_handler_adapters.do_GET(self, r=sys.modules[__name__])

    def transcribe_browser_audio(self):
        return http_handler_adapters.transcribe_browser_audio(self, r=sys.modules[__name__])

    def do_POST(self):
        return post_request_entry.dispatch(self, handle_post=self.handle_post)

    def handle_post(self):
        return turn_http_entry.handle_post(self, r=sys.modules[__name__])

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
    return legacy_response_adapters.run_custom_routine(name, action_results, approved=approved, parameters=parameters, r=sys.modules[__name__])

def run_routine(period, *, action_results=None, movie_action=None, movie_room="lounge", movie_app=None, approved=False):
    return legacy_response_adapters.run_routine(period, action_results=action_results, movie_action=movie_action, movie_room=movie_room, movie_app=movie_app, approved=approved, r=sys.modules[__name__])

def format_routine_result(result, request_id, routine_id, period, movie_action, action_results):
    return legacy_response_adapters.format_routine_result(result, request_id, routine_id, period, movie_action, action_results, r=sys.modules[__name__])

def run_sexy_time(operation, connection, *, approved=False):
    return legacy_response_adapters.run_sexy_time(operation, connection, approved=approved, r=sys.modules[__name__])

def launch_movie_app(connection, remote, app):
    return legacy_response_adapters.launch_movie_app(connection, remote, app, r=sys.modules[__name__])

def start_dinner(connection, *, approved=False):
    return legacy_response_adapters.start_dinner(connection, approved=approved, r=sys.modules[__name__])

def guest_assignment(operation, connection):
    return legacy_response_adapters.guest_assignment(operation, connection, r=sys.modules[__name__])

def set_switch_as_light(name, desired_state, inventory, connection, *, preview=False, action_results=None):
    return legacy_response_adapters.set_switch_as_light(name, desired_state, inventory, connection, preview=preview, action_results=action_results, r=sys.modules[__name__])

def guarded_openai_fallback(message, *, source, exposed_entities=()):
    return legacy_response_adapters.guarded_openai_fallback(message, source=source, exposed_entities=exposed_entities, r=sys.modules[__name__])

def preview_routine(phrase, origin=None):
    return legacy_response_adapters.preview_routine(phrase, origin, r=sys.modules[__name__])
if __name__ == "__main__":
    declan_logs.install()
    main()



