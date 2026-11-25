"""Bind the conversation agent to live services for one HTTP turn."""
import logging
import os
import sqlite3

from declan.ai import conversation_agent, general_chat
from declan.ai.action_evidence_buffer import extend_action_evidence
from declan.ai.action_executor import execute_verified, summarise_result
from declan.ai.fallback_action_evidence import FallbackActionEvidence
from declan.ai.fallback_entity_authorization import exposed_entities
from declan.core import diagnostics, history
from declan.core.execution_results import Outcome
from declan.ha import ha_dispatcher, ha_inventory, lighting_intents, script_discovery
from declan.ha.ha_action_preflight import preflight
from declan.music import approved_media_players, music
from declan.timers import timers
from declan.turn import (
    conversation_turn,
    sensitive_confirmation_decision,
    sensitive_confirmation_resolution,
    sensitive_confirmation_response,
    sensitive_confirmation_turn,
)
from declan.turn.turn_dispatch_orchestration import DispatchResult

LOGGER = logging.getLogger(__name__)


def _result_factory(reply, outcome, base=None, lighting_context=None):
    def field(name):
        return getattr(base, name) if base is not None else None
    return DispatchResult(reply, outcome, field("routine_status"), field("routine_turn"),
                          field("routine_voice_result"),
                          lighting_context if lighting_context is not None else field("lighting_context"),
                          field("information_context"), field("status_target"), field("light_result"))


def house_context(handler, body, *, origin_device, satellite, services):
    """(connection, inventory rows, context) from trusted HA data, for the agent and local help."""
    connection = None
    try:
        connection = services.ha_device_connection()
    except (OSError, ValueError):
        connection = None
    rows = []
    if connection is not None:
        inventory = ha_inventory.InventoryResult.coerce(services.read_ha_inventory_result(connection))
        rows = list(inventory.inventory or []) if inventory.error is None else []
    exposed = exposed_entities(body, handler.headers.get("Authorization", ""),
                               os.environ.get("DECLAN_ASSIST_TOKEN", ""))
    scripts: tuple = ()
    if connection is not None:
        discovery = script_discovery.discover_result(connection)
        scripts = discovery.scripts if discovery.error is None else ()
    try:
        music_rooms = set((approved_media_players.load() or {}).keys())
    except (OSError, ValueError):
        music_rooms = set()
    try:
        from declan.ai import ai_settings
        allowed = ai_settings.read()["allowed_domains"]
    except (OSError, ValueError, sqlite3.Error):
        allowed = []
    context = conversation_turn.gather(
        connection=connection, inventory_rows=rows, exposed=exposed if isinstance(exposed, (list, tuple)) else (),
        origin_device=origin_device or satellite, read_areas=services.read_ha_areas,
        music_rooms=music_rooms, scripts=scripts, phrases=script_discovery.phrases, allowed_domains=allowed)
    return connection, rows, context


def listener_persona(services):
    """Personality sliders for whoever is listening (household or guests)."""
    from declan.turn import personality_dials
    audience = personality_dials.current_audience()
    if not personality_dials.audience_known():
        try:
            audience = personality_dials.audience_for(services.read_guest_mode(), services.read_visitors_present())
        except (AttributeError, OSError, ValueError, TypeError):
            audience = "household"
    return personality_dials.dials(audience)


def run(handler, body, *, message, session_id, source, scope, origin_device, satellite,
        action_results, dispatch, services, local_result=None):
    """Return an AgentTurn, or None to continue with the existing behaviour."""
    connection, _, context = house_context(handler, body, origin_device=origin_device,
                                           satellite=satellite, services=services)
    checks = (
        lambda phrase: lighting_intents.matches(phrase, services.parse_light_command),
        lambda phrase: music.parse(phrase) is not None,
        lambda phrase: music.parse_control(phrase) is not None,
        timers.matches,
    )
    try:
        decision, permitted = conversation_turn.decide(
            message, context, session_id=session_id, scope=scope, checks=checks,
            persona=listener_persona(services))
    except general_chat.ModelUnavailable as error:
        LOGGER.info("Conversation agent unavailable: %s", error)
        return None
    except (ValueError, TypeError, KeyError, OSError, sqlite3.Error) as error:
        LOGGER.warning("Conversation agent failed (%s)", type(error).__name__)
        return None

    def run_devices(actions, permitted_rows, live_connection):
        checked = preflight(tuple(actions), list(permitted_rows.values()))
        results = execute_verified(checked, lambda action: ha_dispatcher.dispatch_result(
            action, live_connection, authorised=lambda candidate: candidate.entity_id in permitted_rows))
        summary = summarise_result(results)
        extend_action_evidence(action_results, tuple(
            FallbackActionEvidence.from_action(result, include_detail=True) for result in summary.actions))
        return summary

    def confirm_command(command):
        normalized = history.normalize_phrase(command)
        session, _, _, reply = sensitive_confirmation_resolution.resolve_confirmation(
            command, normalized, session_id, source=source, satellite=satellite,
            origin_device=origin_device, speaker=body.get("speaker"),
            confirm=sensitive_confirmation_turn.confirmation_turn_result,
            evaluate=sensitive_confirmation_decision.evaluate_result,
            confirmation_response=sensitive_confirmation_response.confirmation_response,
            normalize=history.normalize_phrase, guest_commands=services.GUEST_COMMANDS,
            confirmations=services.SENSITIVE_CONFIRMATIONS, record=history.record,
            diagnostic_id=diagnostics.current_id, log_error=handler.log_error,
            resolve=sensitive_confirmation_resolution.resolved_confirmation,
            effective_message=command,
        )
        if reply is not None:
            conversation_turn.remember(session or session_id, scope, message,
                                       reply.get("reply", "") if isinstance(reply, dict) else "", asked=True)
        return reply

    agent_turn = conversation_turn.execute(
        decision, permitted, connection=connection,
        dispatch_command=lambda command: dispatch(history.normalize_phrase(command)),
        confirm_command=confirm_command, run_devices=run_devices, result_factory=_result_factory)
    lesson = conversation_turn.learnable(
        message, decision, agent_turn.command_result,
        rooms=set(context["areas"]) | set(context["music_rooms"]),
        vague=conversation_turn.prefers_agent(history.normalize_phrase(message), parse_music=music.parse))
    if lesson:
        try:
            # Never overwrites something you taught; next time it's instant and free.
            history.teach_phrase(*lesson, automatic=True, source="conversation")
            LOGGER.info("Conversation agent learned a phrase")
        except (ValueError, OSError, sqlite3.Error):
            LOGGER.warning("Could not save a learned conversation phrase")
    return agent_turn


# Re-exported for tests and diagnostics.
AGENT_DOMAINS = conversation_agent.AGENT_DOMAINS
UNRESOLVED = Outcome.UNRESOLVED
