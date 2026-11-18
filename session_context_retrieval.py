"""Scope-bound retrieval of recent conversation context."""

from math import isfinite


def recent_context(previous, scope, *, now, idle_seconds):
    """Return recent lighting, device and information context for this scope."""
    lights, device, information = (), None, None
    if scope is None or not isinstance(previous, dict):
        return lights, device, information
    # Reject corrupt, non-finite and future timestamps just like active-session expiry.
    at = previous.get("at")
    if (type(at) not in (int, float) or not isfinite(at)
            or at > now or now - at >= idle_seconds):
        return lights, device, information
    if previous.get("device_status_scope") == scope:
        device = previous.get("device_status_target")
    if previous.get("lighting_scope") == scope:
        lights = previous.get("lighting_context", ())
    if previous.get("information_scope") == scope:
        information = previous.get("information_context")
    return lights, device, information
