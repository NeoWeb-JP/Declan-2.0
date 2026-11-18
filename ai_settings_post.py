"""Authorised AI settings POST adapter.

Request authentication, content type and body size checks remain in server.py.
"""

import sqlite3


def handle_ai_settings(handler, body, *, replace_key, save, configured):
    try:
        if not isinstance(body, dict):
            raise ValueError("Invalid AI settings payload")
        if set(body) == {"api_key"}:
            replace_key(body["api_key"])
            handler.send_json(200, {"key_configured": True})
        elif set(body) == {"settings"}:
            handler.send_json(200, {
                "settings": save(body["settings"]),
                "key_configured": configured(),
            })
        else:
            raise ValueError("Invalid AI settings payload")
    except ValueError as error:
        handler.send_json(400, {"error": str(error)})
    except (OSError, sqlite3.Error):
        handler.send_json(503, {"error": "Could not save AI settings."})
