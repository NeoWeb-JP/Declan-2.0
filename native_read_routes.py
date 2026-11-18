"""Native read-only HTTP orchestration after the server's access gates."""
import sqlite3

ROUTES = frozenset({
    "/api/native/settings-status", "/api/native/settings-export",
    "/api/native/settings-recovery", "/api/native/routine-responses",
    "/api/native/routines", "/api/native/intents", "/api/native/logs",
    "/api/native/diagnostics", "/api/native/diagnostics/metrics",
})


def handles(path):
    return path in ROUTES


def dispatch(handler, *, music, configuration, script_discovery,
             ha_connection, command_responses, history, logs, diagnostics):
    path = handler.path
    if path == "/api/native/settings-status":
        try:
            _, source = music.spotify_credentials()
            handler.send_json(200, {"spotify_configured": source in {"saved", "environment"},
                                    "spotify_source": source})
        except (OSError, ValueError):
            handler.send_json(503, {"error": "Spotify configuration status unavailable."})
    elif path in {"/api/native/settings-export", "/api/native/settings-recovery"}:
        try:
            document = (configuration.recovery() if path.endswith("recovery")
                        else configuration.export())
            handler.send_json(200, {"document": document})
        except (OSError, ValueError, sqlite3.Error):
            handler.send_json(503, {"error": "Settings document unavailable."})
    elif path == "/api/native/routine-responses":
        discovery = script_discovery.discover_result(ha_connection(), fresh=True)
        if discovery.error is not None:
            handler.send_json(200, {"commands": command_responses.catalog(), "routines": [],
                                    "routine_error": "Home Assistant routines unavailable. Try again."})
        else:
            handler.send_json(200, {"commands": command_responses.catalog(),
                                    "routines": [{"entity_id": row["entity_id"], "name": row["name"]}
                                                 for row in discovery.scripts]})
    elif path == "/api/native/routines":
        handler.send_json(410, {"error": "Routine mappings are retired. Home Assistant scripts are the source of truth."})
    elif path == "/api/native/intents":
        try:
            handler.send_json(200, {"intents": history.learned_intents()})
        except (OSError, sqlite3.Error):
            handler.send_json(503, {"error": "Learned intentions unavailable."})
    elif path == "/api/native/logs":
        handler.send_json(200, {"entries": logs.recent()})
    elif path == "/api/native/diagnostics/metrics":
        try:
            handler.send_json(200, {"metrics": diagnostics.metrics()})
        except (OSError, ValueError, sqlite3.Error):
            handler.send_json(503, {"error": "Diagnostic metrics unavailable."})
    elif path == "/api/native/diagnostics":
        try:
            handler.send_json(200, {"traces": diagnostics.recent()})
        except (OSError, ValueError, sqlite3.Error):
            handler.send_json(503, {"error": "Diagnostics unavailable."})
    else:
        raise ValueError("Unsupported native read route")
