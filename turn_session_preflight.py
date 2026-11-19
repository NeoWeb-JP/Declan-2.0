"""Session acquisition and voice-turn preflight, retaining live server dependencies."""

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


def prepare(handler, body, message, session_id, *, r):
    turn_session_entry = r.turn_session_entry
    CAPTURE_ARBITER = r.CAPTURE_ARBITER
    history = r.history
    secrets = r.secrets
    SESSION_STORE = r.SESSION_STORE
    monotonic = r.monotonic
    IDLE_SECONDS = r.IDLE_SECONDS
    session_context_retrieval = r.session_context_retrieval
    turn_preflight_entry = r.turn_preflight_entry
    preprocess_speech = r.preprocess_speech
    retry_learning = r.retry_learning
    retry_context = r.retry_context
    converse = r.converse
    retry_cancellation = r.retry_cancellation
    sensitive_confirmation_turn = r.sensitive_confirmation_turn
    sensitive_confirmation_decision = r.sensitive_confirmation_decision
    sensitive_confirmation_response = r.sensitive_confirmation_response
    GUEST_COMMANDS = r.GUEST_COMMANDS
    SENSITIVE_CONFIRMATIONS = r.SENSITIVE_CONFIRMATIONS
    diagnostics = r.diagnostics
    sensitive_confirmation_resolution = r.sensitive_confirmation_resolution
    turn = turn_session_entry.prepare(        self, body, message=message, session_id=session_id,        arbiter=CAPTURE_ARBITER, normalize=history.normalize_phrase,        new_session_id=secrets.token_urlsafe, session_store=SESSION_STORE,        now=monotonic(), idle_seconds=IDLE_SECONDS,        retrieve=session_context_retrieval.recent_context,    )    if turn is None:        return    source, scope, origin_device, satellite = turn.source, turn.scope, turn.origin_device, turn.satellite    last_lights, last_device, last_information = turn.recent_context    routine_reply = outcome = routine_status = None    action_results = ActionEvidenceBuffer()    light_result = None    lighting_context = None    status_target = None    information_context = None    preflight = turn_preflight_entry.resolve(        self, body, message=message, session_id=session_id,        scope=scope, source=source, satellite=satellite,        origin_device=origin_device, session_store=SESSION_STORE,        now=monotonic(),        preprocess=preprocess_speech, normalize=history.normalize_phrase,        learned_intent=history.learned_intent,        retry_window=retry_learning.WINDOW_SECONDS,        consume_retry=retry_context.consume_pending_retry,        cancel_phrases=retry_learning.CANCEL, converse=converse,        record=history.record, cancel_retry=retry_cancellation.cancel_retry_result,        confirm=sensitive_confirmation_turn.confirmation_turn_result,        evaluate=sensitive_confirmation_decision.evaluate_result,        confirmation_response=sensitive_confirmation_response.confirmation_response,        guest_commands=GUEST_COMMANDS, confirmations=SENSITIVE_CONFIRMATIONS,        diagnostic_id=diagnostics.current_id,        resolve_confirmation=sensitive_confirmation_resolution.resolved_confirmation,    )    if preflight is None:        return    session_id, phrase, effective_message = preflight.session_id, preflight.phrase, preflight.effective_message    pending_retry = preflight.pending_retry    return PreparedTurn(session_id, phrase, effective_message, pending_retry,
                        source, scope, origin_device, satellite,
                        last_lights, last_device, last_information)
