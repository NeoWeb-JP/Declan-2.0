"""Assist POST bearer authentication and throttled HTTP responses."""

import secrets


def authenticate_assist(handler, *, token):
    """Return True when an Assist request has been rejected or throttled."""
    supplied = handler.headers.get("Authorization", "")
    valid = bool(token) and secrets.compare_digest(
        supplied.encode(), f"Bearer {token}".encode(),
    )
    retry = handler.server.bad_tokens.check(handler.client_address[0], valid)
    if retry:
        handler.close_connection = True
        handler.send_response(429)
        handler.send_header("Retry-After", str(retry))
        handler.send_header("Content-Length", "0")
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        return True
    if not valid:
        handler.close_connection = True
        handler.send_json(401, {"error": "Invalid bridge credentials."})
        return True
    return False
