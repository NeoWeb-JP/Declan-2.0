"""Pre-dispatch voice turn resolution and early reply handling."""
from dataclasses import dataclass

from declan.turn import learned_intent_resolution
from declan.turn import retry_cancellation_access
from declan.turn import sensitive_confirmation_resolution
from declan.turn import session_context_access


@dataclass(frozen=True)
class PreparedTurn:
    session_id: str
    phrase: str
    effective_message: str
    pending_retry: object


def resolve(handler, body, *, message, session_id, scope, source,
            satellite, origin_device, sessions, lock, now, preprocess,
            normalize, learned_intent, retry_window, consume_retry,
            cancel_phrases, converse, record, cancel_retry, confirm,
            evaluate, confirmation_response, guest_commands, confirmations,
            diagnostic_id, resolve_confirmation):
    effective_message, phrase = learned_intent_resolution.resolve(
        message, preprocess=preprocess, normalize=normalize,
        learned_intent=learned_intent, log_error=handler.log_error,
    )
    pending_retry = session_context_access.consume_retry_context(
        session_id=session_id, scope=scope, sessions=sessions,
        lock=lock, now=now, window_seconds=retry_window,
        consume=consume_retry,
    )
    if pending_retry and normalize(message) in cancel_phrases:
        cancellation = retry_cancellation_access.cancel_pending_retry(
            message=message, session_id=session_id, scope=scope,
            source=source, speaker=body.get("speaker"),
            lock=lock, converse=converse, record=record,
            log_error=handler.log_error, cancel=cancel_retry,
        )
        handler.send_json(200, cancellation.to_wire())
        return None
    session_id, phrase, effective_message, confirmation_reply = (
        sensitive_confirmation_resolution.resolve_confirmation(
            message, phrase, session_id, source=source,
            satellite=satellite, origin_device=origin_device,
            speaker=body.get("speaker"), confirm=confirm,
            evaluate=evaluate, confirmation_response=confirmation_response,
            normalize=normalize, guest_commands=guest_commands,
            confirmations=confirmations, record=record,
            diagnostic_id=diagnostic_id, log_error=handler.log_error,
            resolve=resolve_confirmation,
            effective_message=effective_message,
        )
    )
    if confirmation_reply is not None:
        handler.send_json(200, confirmation_reply)
        return None
    return PreparedTurn(
        session_id=session_id, phrase=phrase,
        effective_message=effective_message, pending_retry=pending_retry,
    )
