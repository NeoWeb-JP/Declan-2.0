"""Resolve guarded fallback and response persona before session finalization."""
from dataclasses import dataclass

from declan.ai import fallback_orchestration
from declan.core.execution_results import Outcome
from declan.turn import response_persona_context


@dataclass(frozen=True)
class PreparedResponse:
    reply: object
    outcome: Outcome | None
    guest_mode: object
    visitor_present: object
    response_guest_mode: object
    information_context: object

    def __post_init__(self):
        if self.outcome is not None:
            object.__setattr__(self, "outcome", Outcome(self.outcome))


def prepare(effective_message, *, routine_reply, outcome, light_result,
            body, authorization, bridge_token, source, action_results,
            exposed_entities, dispatch_fallback, fallback_handler,
            guest_mode_reader, visitors_reader, personality_policy,
            chat_commands, information_context, chat_handler=None):
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
    # D4: a conversational question nothing else answered may get a short,
    # device-free chat reply. An empty AI plan counts as "not answered".
    if chat_handler is not None and light_result is None and (
            routine_reply is None or (fallback is not None and _empty_plan(fallback))):
        try:
            chat_reply = chat_handler(effective_message, source=source, chat_commands=chat_commands)
        except (OSError, ValueError, TypeError):
            chat_reply = None
        if isinstance(chat_reply, str) and chat_reply:
            routine_reply, outcome = chat_reply, Outcome.CHAT_ANSWER
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


def _empty_plan(result):
    from declan.ai.guarded_fallback import EMPTY_PLAN_REPLY
    return result.outcome is Outcome.UNRESOLVED and result.reply == EMPTY_PLAN_REPLY
