"""Bounded, origin-scoped retry context for conversational corrections."""

from math import isfinite


def consume_pending_retry(session, scope, *, now, window_seconds):
    """Consume the pending retry exactly once and reject expired or foreign scopes."""
    if not isinstance(session, dict):
        return None
    pending = session.pop("pending_retry", None)
    if not isinstance(pending, dict):
        return None
    at = pending.get("at")
    if (not isinstance(scope, str) or not scope
            or pending.get("scope") != scope
            or type(now) not in (int, float) or not isfinite(now)
            or type(window_seconds) not in (int, float)
            or not isfinite(window_seconds) or window_seconds < 0
            or type(at) not in (int, float) or not isfinite(at)
            or at > now or now - at > window_seconds):
        return None
    return pending
