"""Orchestrate an HTTP conversation turn using the per-request TurnServices."""
import logging

from declan.http import post_ingress_orchestration
from declan.turn import (
    conversation_turn,
    local_help,
    turn_dispatch_orchestration,
    turn_response_completion,
    turn_session_preflight,
)

LOGGER = logging.getLogger(__name__)


def handle_post(handler, *, services):
    prepared = post_ingress_orchestration.prepare(handler, services=services)
    if prepared is None:
        return
    body, message, session_id = prepared
    turn = turn_session_preflight.prepare(
        handler, body, message, session_id, services=services,
    )
    if turn is None:
        return
    session_id, phrase, effective_message = turn.session_id, turn.phrase, turn.effective_message
    pending_retry = turn.pending_retry
    source, scope, origin_device, satellite = turn.source, turn.scope, turn.origin_device, turn.satellite
    last_lights, last_device, last_information = turn.last_lights, turn.last_device, turn.last_information
    action_results = services.ActionEvidenceBuffer()

    def dispatch(command_phrase):
        return turn_dispatch_orchestration.dispatch(
            command_phrase, source=source, origin_device=origin_device,
            satellite=satellite, action_results=action_results,
            scope=scope, last_lights=last_lights,
            last_device=last_device, last_information=last_information,
            services=services,
        )

    from declan.ai import general_chat
    from declan.music import music
    agent_on = _conversation_enabled(general_chat)
    help_request = local_help.match(effective_message)
    if help_request is not None:
        dispatch_result = _local_help(handler, body, help_request, origin_device=origin_device,
                                      satellite=satellite, services=services, conversation_on=agent_on)
    else:
        dispatch_result = None
    if dispatch_result is not None:
        pass  # Answered locally and for free.
    elif agent_on and conversation_turn.prefers_agent(phrase, parse_music=music.parse):
        dispatch_result = None  # "play something": let the agent choose, not Spotify's literal search.
    else:
        dispatch_result = dispatch(phrase)
    if (help_request is None and not agent_on and conversation_turn.needs_agent(dispatch_result)
            and conversation_turn.needs_conversation(effective_message, services.CHAT_COMMANDS)):
        # The device planner cannot answer "where is Peru?"; say how to turn answers on
        # instead of spending money on a plan that is bound to be refused.
        from declan.core.execution_results import Outcome
        from declan.turn import conversation_entry
        dispatch_result = conversation_entry._result_factory(
            conversation_turn.CONVERSATION_OFF_REPLY, Outcome.UNRESOLVED)
    agent_turn = None
    if help_request is None and agent_on and conversation_turn.needs_agent(dispatch_result):
        from declan.turn import conversation_entry
        agent_turn = conversation_entry.run(
            handler, body, message=message, session_id=session_id, source=source,
            scope=scope, origin_device=origin_device, satellite=satellite,
            action_results=action_results, dispatch=dispatch, services=services,
            local_result=dispatch_result,
        )
        if agent_turn is not None and agent_turn.immediate_reply is not None:
            handler.send_json(200, agent_turn.immediate_reply)
            return
        if agent_turn is not None:
            dispatch_result = agent_turn.dispatch_result
    if dispatch_result is None:
        dispatch_result = dispatch(phrase)
    response = turn_response_completion.complete(
        handler, body=body, message=message, effective_message=effective_message,
        session_id=session_id, phrase=phrase, source=source, scope=scope,
        pending_retry=pending_retry, action_results=action_results,
        dispatch_result=dispatch_result, services=services,
    )
    wire = response.to_wire()
    if agent_turn is not None:
        if agent_turn.follow_up:
            # Keep the microphone open for the answer to Declan's question.
            wire["continue_conversation"] = True
            wire["follow_up_timeout"] = 10
        conversation_turn.remember(wire.get("session_id"), scope, message, wire.get("reply") or "",
                                   asked=agent_turn.follow_up)
    handler.send_json(200, wire)


def _conversation_enabled(general_chat):
    try:
        return general_chat.enabled()
    except (OSError, ValueError):
        return False


def _local_help(handler, body, request, *, origin_device, satellite, services, conversation_on):
    from declan.core.execution_results import Outcome
    from declan.turn import conversation_entry
    try:
        _, rows, context = conversation_entry.house_context(
            handler, body, origin_device=origin_device, satellite=satellite, services=services)
        reply = local_help.answer(request, rows=rows, context=context, conversation_on=conversation_on)
    except (OSError, ValueError, TypeError, KeyError) as error:
        LOGGER.warning("Local help failed (%s)", type(error).__name__)
        return None
    return conversation_entry._result_factory(reply, Outcome.CHAT_ANSWER) if reply else None
