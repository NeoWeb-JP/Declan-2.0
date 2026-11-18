"""Operational GET routes behind server.py's existing access checks."""
import json
import sqlite3
import subprocess  # nosec B404 - only catching errors from trusted release checks

ROUTES = frozenset({
    "/api/ha-status", "/api/updates/status", "/api/updates",
    "/api/settings/export", "/api/settings/export-learning",
    "/api/settings/recovery", "/api/settings/recovery-learning",
})


def handles(path):
    return path in ROUTES


def dispatch(handler, *, ha_status, release_version, updates, configuration):
    path = handler.path
    if path == "/api/ha-status":
        handler.send_json(200, {"status": ha_status().status.value,
                                "release_version": release_version})
    elif path == "/api/updates/status":
        handler.send_json(200, {**updates.status_result().to_wire(),
                                "current": release_version})
    elif path == "/api/updates":
        try:
            handler.send_json(200, {**updates.status_result().to_wire(),
                                    "current": release_version, "versions": updates.check()})
        except (OSError, ValueError, subprocess.SubprocessError):
            handler.send_json(503, {"error": "Couldn't check GitHub for releases."})
    elif path in {"/api/settings/export", "/api/settings/export-learning",
                  "/api/settings/recovery", "/api/settings/recovery-learning"}:
        try:
            document = (configuration.recovery(path.endswith("recovery-learning"))
                        if "/recovery" in path else
                        configuration.export(path.endswith("export-learning")))
            handler.send_body(200, json.dumps(document).encode(),
                              "application/json", "declan-settings.json")
        except (ValueError, OSError, sqlite3.Error):
            handler.send_json(503, {"error": "Settings export is unavailable."})
    else:
        raise ValueError("Unsupported operational read route")
