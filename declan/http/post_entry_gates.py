"""Pre-body POST entry gates, preserving authentication and STT ordering."""

from declan.http import post_request_entry


def enforce(handler, *, assist_token, ingress, authenticate_assist,
            enforce_known_route, enforce_origin, transcribe):
    """Return False when a gate handled the request; True for JSON body parsing.

    STT is dispatched after authentication but before the JSON content-type gate.
    """
    if not post_request_entry.enforce_preflight(
        handler, assist_token=assist_token, ingress=ingress,
        authenticate_assist=authenticate_assist,
        enforce_known_route=enforce_known_route,
        enforce_origin=enforce_origin,
    ):
        return False
    if handler.path == "/api/stt":
        transcribe()
        return False
    return post_request_entry.enforce_content_type(handler)
