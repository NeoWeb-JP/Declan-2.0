"""Prepare and atomically finalize voice-turn responses using the per-request TurnServices."""

import os
from declan.ai import fallback_entity_authorization
from declan.ai import guarded_fallback_dispatch
from declan.core import diagnostics
from declan.core import history
from declan.ha import lighting_intents
from declan.music import music
from declan.turn import command_responses
from declan.turn import conversation_persistence
from declan.turn import personality_policy
from declan.turn import response_composition
from declan.turn import retry_learning
from declan.turn import retry_training_persistence
from declan.turn import routine_responses
from declan.turn import session_turn_state
from declan.turn import turn_atomic_finalization
from declan.turn import turn_context_preparation
from declan.turn import turn_finalization
from declan.turn import turn_persistence_orchestration
from declan.turn import turn_response_composition
from declan.turn import turn_response_orchestration
from declan.turn import turn_response_preparation
def complete(handler, *, body, message, effective_message, session_id, phrase,
             source, scope, pending_retry, action_results, dispatch_result, services):
    guarded_openai_fallback_result = services.guarded_openai_fallback_result
    read_guest_mode = services.read_guest_mode
    read_visitors_present = services.read_visitors_present
    CHAT_COMMANDS = services.CHAT_COMMANDS
    SESSION_STORE = services.SESSION_STORE
    monotonic = services.monotonic
    parse_light_command = services.parse_light_command
    UNMATCHED_REPLY = services.UNMATCHED_REPLY
    converse = services.converse
    routine_reply, outcome = dispatch_result.reply, dispatch_result.outcome
    routine_status, routine_turn = dispatch_result.routine_status, dispatch_result.routine_turn
    routine_voice_result = dispatch_result.routine_voice_result
    lighting_context, information_context = dispatch_result.lighting_context, dispatch_result.information_context
    status_target, light_result = dispatch_result.status_target, dispatch_result.light_result
    response_preparation = turn_response_preparation.prepare(
        effective_message, routine_reply=routine_reply, outcome=outcome,
        light_result=light_result, body=body,
        authorization=handler.headers.get("Authorization", ""),
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
        personality_lines=__import__("declan.turn.personality", fromlist=["LINES"]).LINES,
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
        log_error=handler.log_error, converse=converse,
    )
    return response
