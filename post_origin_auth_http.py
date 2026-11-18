"""Local-origin and scoped bearer access for non-Assist POST routes."""

import secrets

BEARER_ALLOWED_PATHS = frozenset({
    "/api/voicepipeline", "/api/settings/ai", "/api/settings/media-players",
    "/api/settings/music-playlists", "/api/chat", "/api/stt",
    "/api/native/spotify-credentials", "/api/native/settings-import",
    "/api/native/intents", "/api/native/routines",
    "/api/native/routine-responses", "/api/updates",
})


def has_scoped_bearer(path, supplied, token):
    return (
        path in BEARER_ALLOWED_PATHS
        and len(token) >= 32
        and secrets.compare_digest(supplied.encode(), f"Bearer {token}".encode())
    )


def is_authorized(*, path, supplied, token, ingress, client_ip, origin, port):
    if has_scoped_bearer(path, supplied, token) or ingress:
        return True
    return client_ip == "127.0.0.1" and origin in {
        f"http://127.0.0.1:{port}", f"http://localhost:{port}",
    }


def enforce_access(handler, *, token, ingress):
    supplied = handler.headers.get("Authorization", "")
    if has_scoped_bearer(handler.path, supplied, token) or ingress:
        return True
    if not is_authorized(
        path=handler.path, supplied=supplied,
        token=token, ingress=ingress, client_ip=handler.client_address[0],
        origin=handler.headers.get("Origin"), port=handler.server.server_port,
    ):
        handler.send_json(403, {"error": "Send requests from the local Declan page."})
        return False
    return True
