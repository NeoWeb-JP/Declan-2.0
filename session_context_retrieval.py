"""Scope-bound retrieval of recent conversation context."""


def recent_context(previous, scope, *, now, idle_seconds):
    """Return recent lighting, device and information context for this scope."""
    lights, device, information = (), None, None
    if scope is None or not previous:
        return lights, device, information
    # Match the existing idle expiry boundary and do not leak across origins.
    if now - previous["at"] >= idle_seconds:
        return lights, device, information
    if previous.get("device_status_scope") == scope:
        device = previous.get("device_status_target")
    if previous.get("lighting_scope") == scope:
        lights = previous.get("lighting_context", ())
    if previous.get("information_scope") == scope:
        information = previous.get("information_context")
    return lights, device, information
