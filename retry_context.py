"""Bounded, origin-scoped retry context for conversational corrections."""

from context_numeric_validation import finite_number
from retry_phrase_validation import valid_retry_phrase
from retry_scope_validation import same_origin_scope

def consume_pending_retry(session, scope, *, now, window_seconds):
    """Consume the pending retry exactly once and reject expired or foreign scopes."""
    if not isinstance(session, dict):
        return None
    pending = session.pop("pending_retry", None)
    if not isinstance(pending, dict):
        return None
    at = pending.get("at")
    text = pending.get("text")
    if (not valid_retry_phrase(text)
            or not same_origin_scope(pending.get("scope"), scope)
            or not finite_number(now)
            or not finite_number(window_seconds) or window_seconds < 0
            or not finite_number(at)
            or at > now or now - at > window_seconds):
        return None
    return pending
