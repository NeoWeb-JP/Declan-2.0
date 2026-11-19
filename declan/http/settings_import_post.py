"""Authorised settings-import POST response adapter.

The HTTP handler retains access checks, body decoding and request size limits.
"""

import sqlite3


def handle_settings_import(handler, body, *, preview, apply):
    try:
        if not isinstance(body, dict) or set(body) - {"document", "confirm", "expected"}:
            raise ValueError("Send a settings file to preview.")
        if body.get("confirm") is True:
            apply(body.get("document"), body.get("expected"))
            handler.send_json(200, {"saved": True})
        elif "confirm" not in body:
            handler.send_json(200, preview(body.get("document")))
        else:
            raise ValueError("Preview the settings before confirming.")
    except ValueError as error:
        handler.send_json(400, {"error": str(error)})
    except (OSError, sqlite3.Error):
        handler.send_json(503, {"error": "Settings could not be imported."})
