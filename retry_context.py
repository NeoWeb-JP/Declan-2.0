"""Bounded, origin-scoped retry context for conversational corrections."""

from math import isfinite


def _finite_number(value):
    """Reject malformed and oversized numeric metadata without raising."""
    if type(value) not in (int, float):
        return False
    try:
        return isfinite(value)
    except OverflowError:
        return False


def consume_pending_retry(session, scope, *, now, window_seconds):
    """Consume the pending retry exactly once and reject expired or foreign scopes."""
    if not isinstance(session, dict):
        return None
    pending = session.pop("pending_retry", None)
    if not isinstance(pending, dict):
        return None
    at = pending.get("at")
    if (not isinstance(scope, (str, tuple)) or not scope or pending.get("scope") != scope
            or not _finite_number(now)
            or not _finite_number(window_seconds) or window_seconds < 0
            or not _finite_number(at)
            or at > now or now - at > window_seconds):
        return None
    return pending
