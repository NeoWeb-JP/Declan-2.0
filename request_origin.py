"""Validated request-origin context for chat and Assist requests."""
import re


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
        origin = tuple(value if type(value) is str and 0 < len(value) <= 128 else None
                       for value in (device_id, user_id))
        origin_device = origin[0]
        scope = (source, *origin, satellite) if any(origin) or satellite else None
    return source, scope, origin_device, satellite
