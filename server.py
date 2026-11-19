"""Local Declan 2.0 chat prototype. Run with python server.py."""
import argparse as argparse
import ipaddress as ipaddress
import logging as logging
import os as os
import secrets as secrets
import sqlite3 as sqlite3
from http.server import BaseHTTPRequestHandler as BaseHTTPRequestHandler
from declan_ingress.http_server import BoundedHTTPServer as ThreadingHTTPServer  # noqa: F401 - compatibility export
from declan.ha import ha_inventory as ha_inventory
from declan.ha import ha_area_switch_actions as ha_area_switch_actions
from declan.ha import household_routine_dispatch as household_routine_dispatch
from declan.ha import ha_speech_transport as ha_speech_transport
from declan.music import music_stop_dispatch as music_stop_dispatch
from declan.ha import movie_ha_helpers as movie_ha_helpers
from declan.turn import bedroom_routine_dispatch as bedroom_routine_dispatch
from declan.music import media_title_search as media_title_search
from declan.ai import ai_fallback_dispatch as ai_fallback_dispatch
from declan.turn import routine_request_selection as routine_request_selection
from declan.turn import routine_execution_dispatch as routine_execution_dispatch
from declan.ha import lighting_execution_dispatch as lighting_execution_dispatch
from declan.ha import ha_household_status as ha_household_status
import server_lifecycle as server_lifecycle
from declan.turn import routine_turn_orchestration as routine_turn_orchestration
from declan.ha import light_command_parsing
from declan.http import post_ingress_orchestration as post_ingress_orchestration
from declan.turn import turn_dispatch_orchestration as turn_dispatch_orchestration
from declan.turn import turn_session_preflight as turn_session_preflight
from declan.turn import turn_response_completion as turn_response_completion
from declan.turn import command_vocabulary
from declan.http import http_handler_adapters
from declan.turn import turn_http_entry
from declan.core import domain_boundary_helpers
from declan.ha import household_selection_boundaries
from declan.core import runtime_dispatch_boundaries
from declan.core import compatibility_facade
from declan.core import service_entry_boundaries
import server_bootstrap
import server_runtime_state
import sys
from pathlib import Path as Path
from threading import Thread as Thread
from time import monotonic as monotonic, sleep as sleep
from urllib.parse import urlsplit as urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler as ProxyHandler, Request as Request, build_opener as build_opener

from declan.core.execution_results import ExecutionResult as ExecutionResult, Outcome as Outcome
from declan.voice.arbitration import CaptureArbiter as CaptureArbiter

from declan.core import conditions as conditions
from declan.turn import sensitive_confirmations as sensitive_confirmations
from declan.core import diagnostics
from declan.core import declan_logs as declan_logs
from declan.core import configuration as configuration
from declan.music import media_search_agents as media_search_agents
from declan.ha import household_entities as household_entities
from declan.http import health_readiness as health_readiness
from declan.voice import voice_profiles as voice_profiles
from declan.voice import voicepipeline as voicepipeline
from declan.ha import device_status as device_status
from declan.turn import retry_learning as retry_learning
from declan.turn import retry_training_persistence as retry_training_persistence
from declan.turn import conversation_persistence as conversation_persistence
from declan.turn import turn_finalization as turn_finalization
from declan.turn import turn_response_orchestration as turn_response_orchestration
from declan.turn import turn_persistence_orchestration as turn_persistence_orchestration
from declan.turn import session_context_retrieval as session_context_retrieval
from declan.turn import retry_context as retry_context
from declan.turn import retry_cancellation as retry_cancellation
from declan.turn import sensitive_confirmation_response as sensitive_confirmation_response
from declan.turn import sensitive_confirmation_decision as sensitive_confirmation_decision
from declan.turn import sensitive_confirmation_turn as sensitive_confirmation_turn
from declan.turn import routine_preview_detection as routine_preview_detection
from declan.turn import routine_preview_dispatch as routine_preview_dispatch
from declan.turn import guest_assignment_command as guest_assignment_command
from declan.turn import roast_command_dispatch as roast_command_dispatch
from declan.timers import timer_command_dispatch as timer_command_dispatch
from declan.ha import lighting_command_dispatch as lighting_command_dispatch
from declan.ha import lighting_context_finalization as lighting_context_finalization
from declan.ai import fallback_entity_authorization as fallback_entity_authorization
from declan.ai import guarded_fallback_dispatch as guarded_fallback_dispatch
from declan.turn import turn_context_preparation as turn_context_preparation
from declan.turn import turn_session_entry as turn_session_entry
from declan.turn import turn_preflight_entry as turn_preflight_entry
from declan.turn import turn_preview_stage as turn_preview_stage
from declan.turn import turn_direct_dispatch as turn_direct_dispatch
from declan.turn import turn_routine_stage as turn_routine_stage
from declan.turn import turn_fallback_dispatch as turn_fallback_dispatch
from declan.turn import turn_response_preparation as turn_response_preparation
from declan.turn import turn_atomic_finalization as turn_atomic_finalization
from declan.turn import turn_response_composition as turn_response_composition
from declan.core import history as history
from declan.http import post_body_routing as post_body_routing
from declan.music import music as music
from declan.music import approved_media_players as approved_media_players
from declan.music import spotify_playlists as spotify_playlists
from declan.music import music_playlists_post as music_playlists_post
from declan.timers import timers as timers
from declan.updates import updates as updates
from declan.http import post_operational_routing as post_operational_routing
from declan.music import media_settings_routes as media_settings_routes
from declan.http import get_request_dispatch as get_request_dispatch
from declan.voice import speech_http_routes as speech_http_routes
from declan.voice import assist_auth_http as assist_auth_http
from declan.http import post_payload_validation as post_payload_validation
from declan.http import post_origin_auth_http as post_origin_auth_http
from declan.http import post_route_gate_http as post_route_gate_http
from declan.http import post_request_entry
from declan.http import post_entry_gates as post_entry_gates
from declan.http import http_response_transport as http_response_transport
from declan.http import http_ingress_security as http_ingress_security
from declan.turn import sensitive_confirmation_resolution as sensitive_confirmation_resolution
from declan.voice import web_stt
from declan.ai import openai_planner
from declan.ai import ai_settings
from declan.ai import ai_credentials
from declan.ai import ai_pricing as ai_pricing
from declan.ai import ai_budget as ai_budget
from declan.ai import ai_context as ai_context
from declan.ai import ai_intent_gate as ai_intent_gate
from declan.ai import guarded_fallback as guarded_fallback
from declan.ha import ha_dispatcher as ha_dispatcher
from declan.turn import routine_registry as routine_registry
from declan.turn.routine_action_evidence import parse_routine_actions as parse_routine_actions
from declan.ha.home_assistant_results import HomeAssistantStatus as HomeAssistantStatus, HomeAssistantStatusResult
from declan.turn.routine_selection_results import RoutineSelection, RoutineTurnSelection
from declan.ha.lighting_action_evidence import LightingActionEvidence as LightingActionEvidence
from declan.ha.movie_action_evidence import MovieActionEvidence as MovieActionEvidence
from declan.ai.action_evidence_buffer import ActionEvidenceBuffer as ActionEvidenceBuffer, append_action_evidence as append_action_evidence, extend_action_evidence as extend_action_evidence
from declan.ai.fallback_action_evidence import FallbackActionEvidence as FallbackActionEvidence
from declan.ha import script_discovery as script_discovery
from declan.turn.intent_preprocessing import preprocess_speech as preprocess_speech
from declan.turn.personality import add_sass as add_sass, choose_line as choose_line
from declan.turn import routine_responses as routine_responses
from declan.turn import routine_follow_on as routine_follow_on
from declan.turn import response_composition as response_composition
from declan.turn import command_responses as command_responses
from declan.turn import command_registry as command_registry
from declan.turn import session_orchestration as session_orchestration
from declan.turn import session_store as session_store
from declan.turn import routine_cooldown as routine_cooldown
from declan.turn import active_routine_registry as active_routine_registry
from declan.turn import routine_execution_gates as routine_execution_gates
from declan.turn import routine_cancellation as routine_cancellation
from declan.turn import session_turn_state as session_turn_state
from declan.ha import lighting_intents as lighting_intents
from declan.turn import roast as roast
from declan.turn import personality_policy as personality_policy

(DECLAN_EVENT_LOG, SESSION_STORE, CAPTURE_ARBITER, SENSITIVE_CONFIRMATIONS,
 ROUTINE_EXECUTION_GATES, ROUTINE_COOLDOWN, ACTIVE_ROUTINE_REGISTRY) = server_runtime_state.create_runtime(
    logging_module=logging, session_module=session_store, arbiter_factory=CaptureArbiter,
    confirmation_factory=sensitive_confirmations.ConfirmationGate,
    gates_factory=routine_execution_gates.RoutineExecutionGates,
    cooldown_factory=routine_cooldown.RoutineCooldown,
    registry_factory=active_routine_registry.ActiveRoutineRegistry,
)

def track_routine(name, script):
    return compatibility_facade.track_routine(name, script, r=sys.modules[__name__])

def stop_pending_routines_result():
    return compatibility_facade.stop_pending_routines_result(r=sys.modules[__name__])

(IDLE_SECONDS, ASSIST_PORT, RELEASE_VERSION, SEXY_TIME_COMMANDS, DINNER_PHRASES,
 GUEST_MODE_ENTITY, GUEST_REGISTER_ENTITY, VISITORS_PRESENT_ENTITY, GUEST_COMMANDS,
 UNMATCHED_REPLY, NAME_PATTERN, CHAT_COMMANDS, GOOD_MORNING_SCRIPT,
 GOOD_MORNING_PHRASES, GOOD_NIGHT_SCRIPT, GOOD_NIGHT_PHRASES) = server_runtime_state.runtime_settings(
    updates_module=updates, vocabulary=command_vocabulary,
)

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def home_assistant_status_result() -> HomeAssistantStatusResult:
    return household_selection_boundaries.home_assistant_status_result(r=sys.modules[__name__])

def configured_guest_mode_entity():
    return household_selection_boundaries.configured_guest_mode_entity(r=sys.modules[__name__])

def read_guest_mode():
    return household_selection_boundaries.read_guest_mode(r=sys.modules[__name__])

def read_visitors_present():
    return household_selection_boundaries.read_visitors_present(r=sys.modules[__name__])

def routine_action_results_typed(steps):
    return compatibility_facade.routine_action_results_typed(steps, r=sys.modules[__name__])

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

def select_routine_turn_result(phrase, origin) -> RoutineTurnSelection | None:
    return household_selection_boundaries.select_routine_turn_result(phrase, origin, r=sys.modules[__name__])

def preview_routine_result(phrase, origin=None):
    return household_selection_boundaries.preview_routine_result(phrase, origin, r=sys.modules[__name__])

def execute_routine_result(selection, action_results, *, approved=False):
    return household_selection_boundaries.execute_routine_result(selection, action_results, approved=approved, r=sys.modules[__name__])

def run_custom_routine_result(name, action_results=None, *, approved=False, parameters=None):
    return service_entry_boundaries.run_custom_routine_result(name, action_results=action_results, approved=approved, parameters=parameters, r=sys.modules[__name__])


def chained_outcome_result(routine, lighting):
    return domain_boundary_helpers.chained_outcome_result(routine, lighting)

def search_media_result(phrase):
    return service_entry_boundaries.search_media_result(phrase, r=sys.modules[__name__])


def launch_movie_app_result(connection, remote, app):
    return service_entry_boundaries.launch_movie_app_result(connection, remote, app, r=sys.modules[__name__])


def discover_movie_entities(connection, room, *, script, remote, needs_remote):
    return service_entry_boundaries.discover_movie_entities(connection, room, script=script, remote=remote, needs_remote=needs_remote, r=sys.modules[__name__])


def verify_legacy_lounge_start(connection, script):
    return service_entry_boundaries.verify_legacy_lounge_start(connection, script, r=sys.modules[__name__])


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
    return service_entry_boundaries.ha_device_connection(r=sys.modules[__name__])


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

def read_ha_inventory_result(connection) -> ha_inventory.InventoryResult:
    return ha_inventory.read_result(connection)


def read_music_inventory_result(connection) -> ha_inventory.InventoryResult:
    return ha_inventory.read_result(connection, music=True)


def stop_everywhere_result(connection):
    """Return a typed stop-all result with playback diagnostics."""
    return _stop_everywhere_typed_core(connection)

def _stop_everywhere_typed_core(connection):
    return music_stop_dispatch.stop_everywhere_result(
        connection, inventory_reader=read_music_inventory_result,
        inventory_module=ha_inventory, music_provider=music,
    )

def stop_origin_result(connection, satellite, device):
    return music_stop_dispatch.stop_origin_result(
        connection, satellite, device, inventory_reader=read_music_inventory_result,
        inventory_module=ha_inventory, music_provider=music, timer_provider=timers,
    )

def read_ha_areas(connection, origin=None):
    return ha_area_switch_actions.read_ha_areas(connection, origin, request_factory=Request)

def set_switch_as_light_result(name, desired_state, inventory, connection, *, preview=False, action_results=None):
    return ha_area_switch_actions.set_switch_as_light_result(
        name, desired_state, inventory, connection,
        preview=preview, action_results=action_results,
        request_factory=Request, append_evidence=append_action_evidence,
        evidence_factory=LightingActionEvidence,
    )

def set_lights(name, desired_state, *, brightness=None, preview=False, require_all=False, relative_step=10,
               action_results=None, origin_device=None):
    """Compatibility API for callers expecting plain reply/outcome strings."""
    return server_bootstrap.set_lights(name, desired_state, brightness=brightness, preview=preview, require_all=require_all, relative_step=relative_step, action_results=action_results, origin_device=origin_device, r=sys.modules[__name__])


def set_lights_result(name, desired_state, *, brightness=None, preview=False, require_all=False, relative_step=10,
               action_results=None, origin_device=None):
    return runtime_dispatch_boundaries.set_lights_result(name, desired_state, brightness=brightness, preview=preview, require_all=require_all, relative_step=relative_step, action_results=action_results, origin_device=origin_device, r=sys.modules[__name__])

def _bounded_ai_plan(message, exposed, settings, usage_sink=None, inventory=None):
    return domain_boundary_helpers.bounded_ai_plan(message, exposed, settings, usage_sink=usage_sink, inventory=inventory, planner=openai_planner, credentials=ai_credentials, money=ai_settings._money)

def guarded_openai_fallback_result(message, *, source, exposed_entities=()):
    return runtime_dispatch_boundaries.guarded_openai_fallback_result(message, source=source, exposed_entities=exposed_entities, r=sys.modules[__name__])

def converse(message, session_id, routine_reply=None, *, lighting_context=None, scope=None, guest_mode=None):
    """Compatibility entry point; caller holds SESSION_STORE.lock."""
    return service_entry_boundaries.converse(message, session_id, routine_reply, lighting_context=lighting_context, scope=scope, guest_mode=guest_mode, r=sys.modules[__name__])


@diagnostics.timed("ha_transcription")
def traced_transcribe_result(*args, **kwargs):
    return web_stt.transcribe_result(*args, **kwargs)


class Handler(BaseHTTPRequestHandler):
    timeout = 5

    def end_headers(self):
        return server_bootstrap.end_headers(self, r=sys.modules[__name__])

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
    return server_bootstrap.main(r=sys.modules[__name__])


if __name__ == "__main__":
    server_bootstrap.run(r=sys.modules[__name__])



