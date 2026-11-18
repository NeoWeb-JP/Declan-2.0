"""Validated request-origin context for chat and Assist requests."""
import re
from retry_scope_validation import assist_scope, normalize_origin_id


def request_context(path, body):
    """Derive source, satellite, origin and conversation scope from a request."""
    source = "assist" if path == "/api/assist" else (
        "browser_voice" if body.get("source") == "voice" else "browser_keyboard"
    )
    scope = source
    origin_device = None
    satellite = body.get("satellite_id") if source == "assist" else None
    if (type(satellite) is not str or len(satellite) > 128
            or not re.fullmatch(r"assist_satellite\.[a-z0-9_]+", satellite)):
        satellite = None
    if source == "assist":
        device_id = body.get("device_id")
        user_id = body.get("user_id")
        origin_device = normalize_origin_id(device_id)
        scope = assist_scope(origin_device, user_id, satellite)
    return source, scope, origin_device, satellite
