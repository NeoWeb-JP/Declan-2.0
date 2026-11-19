"""Session acquisition and voice-turn preflight, using the per-request TurnServices."""

import secrets
from declan.core import diagnostics
from declan.core import history
from declan.turn import retry_cancellation
from declan.turn import retry_context
from declan.turn import retry_learning
from declan.turn import sensitive_confirmation_decision
from declan.turn import sensitive_confirmation_resolution
from declan.turn import sensitive_confirmation_response
from declan.turn import sensitive_confirmation_turn
from declan.turn import session_context_retrieval
from declan.turn import turn_preflight_entry
from declan.turn import turn_session_entry
from dataclasses import dataclass


@dataclass(frozen=True)
class PreparedTurn:
    session_id: str
    phrase: str
    effective_message: str
    pending_retry: object
    source: object
    scope: object
    origin_device: object
    satellite: object
    last_lights: object
    last_device: object
    last_information: object


def prepare(handler, body, message, session_id, *, services):
    CAPTURE_ARBITER = services.CAPTURE_ARBITER
    SESSION_STORE = services.SESSION_STORE
    monotonic = services.monotonic
    IDLE_SECONDS = services.IDLE_SECONDS
    preprocess_speech = services.preprocess_speech
    converse = services.converse
    GUEST_COMMANDS = services.GUEST_COMMANDS
    SENSITIVE_CONFIRMATIONS = services.SENSITIVE_CONFIRMATIONS
    turn = turn_session_entry.prepare(
        handler, body, message=message, session_id=session_id,
        arbiter=CAPTURE_ARBITER, normalize=history.normalize_phrase,
        new_session_id=secrets.token_urlsafe, session_store=SESSION_STORE,
        now=monotonic(), idle_seconds=IDLE_SECONDS,
        retrieve=session_context_retrieval.recent_context,
    )
    if turn is None:
        return
    source, scope, origin_device, satellite = turn.source, turn.scope, turn.origin_device, turn.satellite
    last_lights, last_device, last_information = turn.recent_context
    preflight = turn_preflight_entry.resolve(
        handler, body, message=message, session_id=session_id,
        scope=scope, source=source, satellite=satellite,
        origin_device=origin_device, session_store=SESSION_STORE,
        now=monotonic(),
        preprocess=preprocess_speech, normalize=history.normalize_phrase,
        learned_intent=history.learned_intent,
        retry_window=retry_learning.WINDOW_SECONDS,
        consume_retry=retry_context.consume_pending_retry,
        cancel_phrases=retry_learning.CANCEL, converse=converse,
        record=history.record, cancel_retry=retry_cancellation.cancel_retry_result,
        confirm=sensitive_confirmation_turn.confirmation_turn_result,
        evaluate=sensitive_confirmation_decision.evaluate_result,
        confirmation_response=sensitive_confirmation_response.confirmation_response,
        guest_commands=GUEST_COMMANDS, confirmations=SENSITIVE_CONFIRMATIONS,
        diagnostic_id=diagnostics.current_id,
        resolve_confirmation=sensitive_confirmation_resolution.resolved_confirmation,
    )
    if preflight is None:
        return
    session_id, phrase, effective_message = preflight.session_id, preflight.phrase, preflight.effective_message
    pending_retry = preflight.pending_retry
    return PreparedTurn(session_id, phrase, effective_message, pending_retry,
                        source, scope, origin_device, satellite,
                        last_lights, last_device, last_information)
