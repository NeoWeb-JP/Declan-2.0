"""GET authentication and local-origin policy, before any route dispatch."""
import secrets
from urllib.parse import urlsplit


def enforce_access(handler, *, ingress, token):
        # The HA integration uses its Assist bearer token for this one read-only
        # endpoint. Do not extend this exception to management or update routes.
        supplied = handler.headers.get("Authorization", "")
        capabilities_auth = (
            handler.path == "/api/capabilities" and len(token) >= 32
            and secrets.compare_digest(supplied.encode(), f"Bearer {token}".encode())
        )
        # Read-only history is accessible to the HA integration using its
        # existing Assist token. All write/export/update routes stay protected.
        history_auth = (
            (urlsplit(handler.path).path == "/api/history"
             or urlsplit(handler.path).path == "/api/history/recording-links"
             or handler.path == "/api/history/quality")
            and len(token) >= 32
            and secrets.compare_digest(supplied.encode(), f"Bearer {token}".encode())
        )
        players_auth = (
            handler.path in {"/api/settings/media-players", "/api/settings/music-playlists", "/api/settings/ai",
                             "/api/settings/music", "/api/settings/speaker"}
            and len(token) >= 32
            and secrets.compare_digest(supplied.encode(), f"Bearer {token}".encode())
        )
        voice_review_auth = (
            handler.path == "/api/voicepipeline"
            and len(token) >= 32
            and secrets.compare_digest(supplied.encode(), f"Bearer {token}".encode())
        )
        native_settings_auth = (
            handler.path in {"/api/native/settings-status", "/api/native/settings-export",
                          "/api/native/settings-recovery", "/api/native/diagnostics", "/api/native/logs", "/api/native/intents", "/api/native/routines", "/api/native/routine-responses"}
            and len(token) >= 32
            and secrets.compare_digest(supplied.encode(), f"Bearer {token}".encode())
        )
        updates_auth = (
            handler.path == "/api/updates/status"
            and len(token) >= 32
            and secrets.compare_digest(supplied.encode(), f"Bearer {token}".encode())
        )
        settings_status_auth = (
            handler.path == "/api/native/settings-status"
            and len(token) >= 32
            and secrets.compare_digest(supplied.encode(), f"Bearer {token}".encode())
        )
        if not ingress and not native_settings_auth and not settings_status_auth and not capabilities_auth and not history_auth and not players_auth and not voice_review_auth and not updates_auth and handler.client_address[0] != "127.0.0.1":
            handler.send_json(403, {"error": "Local access only."})
            return False
        if not ingress and not native_settings_auth and not history_auth and not players_auth and not voice_review_auth and not updates_auth and (
            handler.path.startswith("/api/history")
            or handler.path.startswith("/api/settings/") or handler.path in {"/api/voice-profiles", "/api/voicepipeline"}
            or handler.path in {"/api/diagnostics", "/api/settings/spotify", "/api/updates", "/api/updates/status"}
        ) and handler.headers.get("Host") not in {
            f"127.0.0.1:{handler.server.server_port}", f"localhost:{handler.server.server_port}"
        }:
            handler.send_json(403, {"error": "Use the local Declan address."})
            return False
        return True
