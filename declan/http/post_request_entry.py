"""POST request entry boundary: diagnostics and early request validation."""

import diagnostics
from declan.http import post_content_type_http
from declan.http import post_request_preflight


_DIAGNOSTIC_ROUTES = frozenset({
    "/api/chat", "/api/assist", "/api/stt", "/api/tts", "/api/assist/history",
})


def dispatch(handler, *, handle_post):
    """Scope request diagnostics to conversation and speech routes only."""
    if handler.path not in _DIAGNOSTIC_ROUTES:
        return handle_post()
    with diagnostics.request(handler.path):
        return handle_post()


def enforce_preflight(handler, *, assist_token, ingress, authenticate_assist,
                      enforce_known_route, enforce_origin):
    """Enforce authentication and request origin before accepting a POST body."""
    return post_request_preflight.enforce(
        handler, assist_token=assist_token, ingress=ingress,
        authenticate_assist=authenticate_assist,
        enforce_known_route=enforce_known_route,
        enforce_origin=enforce_origin,
    )


def enforce_content_type(handler):
    """Reject unsupported POST payload types before parsing request bodies."""
    return post_content_type_http.enforce_json_content_type(handler)
