"""Resolve guarded fallback and response persona before session finalization."""
from dataclasses import dataclass

import fallback_orchestration
import response_persona_context


@dataclass(frozen=True)
class PreparedResponse:
    reply: object
    outcome: object
    guest_mode: object
    visitor_present: object
    response_guest_mode: object
    information_context: object


def prepare(effective_message, *, routine_reply, outcome, light_result,
            body, authorization, bridge_token, source, action_results,
            exposed_entities, dispatch_fallback, fallback_handler,
            guest_mode_reader, visitors_reader, personality_policy,
            chat_commands, information_context):
    fallback = fallback_orchestration.resolve_fallback_result(
        effective_message, routine_reply=routine_reply,
        light_result=light_result, body=body,
        authorization=authorization, bridge_token=bridge_token,
        source=source, action_results=action_results,
        exposed_entities=exposed_entities,
        dispatch_fallback=dispatch_fallback,
        fallback_handler=fallback_handler,
    )
    if fallback is not None:
        routine_reply, outcome = fallback.reply, fallback.outcome
    guest_mode, visitor_present, response_guest_mode = (
        response_persona_context.resolve_response_persona(
            guest_mode_reader, visitors_reader, personality_policy,
        )
    )
    chat_kind = effective_message.casefold().strip(" .?!")
    if routine_reply is None and chat_commands.get(chat_kind) == "time":
        information_context = ("time", None, None)
    return PreparedResponse(
        reply=routine_reply, outcome=outcome,
        guest_mode=guest_mode, visitor_present=visitor_present,
        response_guest_mode=response_guest_mode,
        information_context=information_context,
    )
