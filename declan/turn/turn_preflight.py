"""Pre-dispatch voice turn resolution and early reply handling."""
import secrets
import sqlite3
from dataclasses import dataclass

from declan.turn import (
    command_style,
    learned_intent_resolution,
    retry_cancellation_access,
    sensitive_confirmation_resolution,
    session_context_access,
)


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
    if _ignored_by_command_style(handler, body, message=message, session_id=session_id,
                                 source=source, pending_retry=pending_retry,
                                 preprocess=preprocess, record=record):
        return None
    return PreparedTurn(
        session_id=session_id, phrase=phrase,
        effective_message=effective_message, pending_retry=pending_retry,
    )


def _ignored_by_command_style(handler, body, *, message, session_id, source,
                              pending_retry, preprocess, record, mode=None):
    """#373: silently end a satellite turn that does not use the chosen style.

    Runs after cancel and confirmation replies, so "stop" and "yes" are never
    gated, and a reply to Declan's own rephrase prompt passes. Nothing is
    dispatched, no retry window opens and nothing is learned.
    """
    try:
        mode = command_style.style() if mode is None else mode
    except (OSError, ValueError):
        mode = "any"
    if mode == "any" or source not in command_style.GATED_SOURCES:
        return False
    try:
        spoken = preprocess(message).commands[0]
    except (ValueError, IndexError, AttributeError):
        spoken = message
    # A self-correction keeps the opener it started with ("can you turn on the
    # kitchen, no I mean the lounge"), so either form may pass.
    reasons = [command_style.rejection(text, mode=mode, source=source, awaiting_reply=bool(pending_retry))
               for text in dict.fromkeys((spoken, message))]
    if any(reason is None for reason in reasons):
        return False
    reason = reasons[0]
    session_id = session_id if isinstance(session_id, str) and session_id else secrets.token_urlsafe(24)
    try:
        record(session_id, source, message, "", "ignored",
               speaker=body.get("speaker") if source == "assist" else None)
    except (OSError, sqlite3.Error):
        handler.log_error("Could not save conversation history.")
    handler.send_json(200, {"reply": "", "session_id": session_id, "outcome": "ignored",
                            "ignored_reason": reason, "continue_conversation": False,
                            "follow_up_timeout": 0})
    return True
