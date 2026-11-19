"""Scope-bound retrieval of recent conversation context."""

from declan.core.context_numeric_validation import finite_number
from declan.turn.retry_scope_validation import same_origin_scope, valid_retry_scope

def recent_context(previous, scope, *, now, idle_seconds):
    """Return recent lighting, device and information context for this scope."""
    lights, device, information = (), None, None
    if (not valid_retry_scope(scope) or not isinstance(previous, dict)
            or not finite_number(now)
            or not finite_number(idle_seconds) or idle_seconds <= 0):
        return lights, device, information
    # Reject corrupt, non-finite and future timestamps just like active-session expiry.
    at = previous.get("at")
    if (not finite_number(at)
            or at > now or now - at >= idle_seconds):
        return lights, device, information
    if same_origin_scope(previous.get("device_status_scope"), scope):
        device = previous.get("device_status_target")
    if same_origin_scope(previous.get("lighting_scope"), scope):
        lights = previous.get("lighting_context", ())
    if same_origin_scope(previous.get("information_scope"), scope):
        information = previous.get("information_context")
    return lights, device, information
