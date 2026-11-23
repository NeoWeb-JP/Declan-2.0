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
from declan.turn import turn_http_entry
from declan.turn import turn_services
from declan.core import domain_boundary_helpers
import server_runtime_state
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
    return ACTIVE_ROUTINE_REGISTRY.track(name, script)

def stop_pending_routines_result():
    return routine_cancellation.stop_pending_routines_result(
        connection_factory=ha_device_connection,
        active_registry=ACTIVE_ROUTINE_REGISTRY,
    )

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

def routine_action_results_typed(steps):
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

def select_routine_result(phrase, origin) -> RoutineSelection | None:
    return routine_request_selection.select_routine_result(
        phrase, origin, connect=ha_device_connection,
        discovery_module=script_discovery, movie_parser=parse_movie_request,
        morning_phrases=GOOD_MORNING_PHRASES, night_phrases=GOOD_NIGHT_PHRASES,
        dinner_phrases=DINNER_PHRASES, sexy_commands=SEXY_TIME_COMMANDS,
    )

def select_routine_turn_result(phrase, origin) -> RoutineTurnSelection | None:
    return routine_turn_orchestration.select_routine_turn_result(
        phrase, origin, select=select_routine_result, parse_movie=parse_movie_request,
    )

def preview_routine_result(phrase, origin=None):
    return routine_turn_orchestration.preview_routine_result(
        phrase, origin, select_turn=select_routine_turn_result,
    )

def execute_routine_result(selection, action_results, *, approved=False):
    return routine_turn_orchestration.execute_routine_result(
        selection, action_results, approved=approved,
        discovery=script_discovery, connect=ha_device_connection,
    )

def run_custom_routine_result(name, action_results=None, *, approved=False, parameters=None):
    return routine_execution_dispatch.run_custom_routine_result(
        name, action_results=action_results, approved=approved, parameters=parameters,
        registry=routine_registry, connect=ha_device_connection, areas_reader=read_ha_areas,
        token_hex=secrets.token_hex, request_factory=Request, tracker=track_routine,
        parse_steps=routine_action_results_typed, extend_evidence=extend_action_evidence,
    )


def chained_outcome_result(routine, lighting):
    return domain_boundary_helpers.chained_outcome_result(routine, lighting)

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
def handle_light_request_result(phrase, *, action_results=None, last_lights=(), origin_device=None):
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


def set_lights_result(name, desired_state, *, brightness=None, preview=False, require_all=False, relative_step=10,
               action_results=None, origin_device=None, colour=None):
    return lighting_execution_dispatch.set_lights_result(
        name, desired_state, brightness=brightness, preview=preview,
        require_all=require_all, relative_step=relative_step,
        action_results=action_results, origin_device=origin_device, colour=colour,
        connect=ha_device_connection, inventory_reader=read_ha_inventory_result,
        inventory_module=ha_inventory, entities=household_entities,
        sass=add_sass, areas_reader=read_ha_areas,
        switch_dispatch=set_switch_as_light_result, intents=lighting_intents,
        evidence_factory=LightingActionEvidence, append_evidence=append_action_evidence,
        clock=monotonic, sleeper=sleep, request_factory=Request,
    )

def _bounded_ai_plan(message, exposed, settings, usage_sink=None, inventory=None):
    return domain_boundary_helpers.bounded_ai_plan(message, exposed, settings, usage_sink=usage_sink, inventory=inventory, planner=openai_planner, credentials=ai_credentials, money=ai_settings._money)

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
        location_reader=ha_inventory.read_locations,
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


def _turn_services() -> turn_services.TurnServices:
    """Resolve server-owned collaborators at call time so patches take effect."""
    return turn_services.TurnServices(
        ActionEvidenceBuffer=ActionEvidenceBuffer,
        CAPTURE_ARBITER=CAPTURE_ARBITER,
        CHAT_COMMANDS=CHAT_COMMANDS,
        GUEST_COMMANDS=GUEST_COMMANDS,
        IDLE_SECONDS=IDLE_SECONDS,
        NoRedirect=NoRedirect,
        ProxyHandler=ProxyHandler,
        RELEASE_VERSION=RELEASE_VERSION,
        SENSITIVE_CONFIRMATIONS=SENSITIVE_CONFIRMATIONS,
        SESSION_STORE=SESSION_STORE,
        UNMATCHED_REPLY=UNMATCHED_REPLY,
        add_sass=add_sass,
        build_opener=build_opener,
        chained_outcome_result=chained_outcome_result,
        configured_guest_mode_entity=configured_guest_mode_entity,
        converse=converse,
        execute_routine_result=execute_routine_result,
        guarded_openai_fallback_result=guarded_openai_fallback_result,
        guest_assignment_result=guest_assignment_result,
        ha_device_connection=ha_device_connection,
        handle_light_request_result=handle_light_request_result,
        monotonic=monotonic,
        parse_light_command=parse_light_command,
        preprocess_speech=preprocess_speech,
        preview_routine_result=preview_routine_result,
        read_guest_mode=read_guest_mode,
        read_ha_areas=read_ha_areas,
        read_ha_inventory_result=read_ha_inventory_result,
        read_music_inventory_result=read_music_inventory_result,
        read_visitors_present=read_visitors_present,
        render_web_voice=render_web_voice,
        routine_action_results_typed=routine_action_results_typed,
        search_media_result=search_media_result,
        select_routine_turn_result=select_routine_turn_result,
        stop_everywhere_result=stop_everywhere_result,
        stop_pending_routines_result=stop_pending_routines_result,
    )


class Handler(BaseHTTPRequestHandler):
    timeout = 5

    def end_headers(self):
        http_ingress_security.send_security_headers(self)
        return BaseHTTPRequestHandler.end_headers(self)

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
        return turn_http_entry.handle_post(self, services=_turn_services())

def main():
    from declan.turn import self_report
    self_report.mark_started()  # FUT-50: "how are you, Declan?" reports uptime from here
    return server_lifecycle.main(
        description=__doc__, argv=None, environ=os.environ,
        history_store=history, timer_store=timers,
        server_factory=ThreadingHTTPServer, handler=Handler,
        thread_factory=Thread, clock=monotonic,
        opener_factory=build_opener, proxy_factory=ProxyHandler,
        logger=DECLAN_EVENT_LOG, updates_module=updates, music_module=music,
        ha_connect=ha_device_connection, music_inventory=read_music_inventory_result,
        ip_address=ipaddress.ip_address, assist_port=ASSIST_PORT,
        run_background=server_lifecycle.single_flight_runner(Thread),
    )


if __name__ == "__main__":
    declan_logs.install()
    main()
