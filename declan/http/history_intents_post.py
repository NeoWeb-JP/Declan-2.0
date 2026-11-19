"""Authorised history intent correction POST adapter."""

import sqlite3


def handle_history_intents(handler, body, *, forget_intent, edit_intent, teach_intent,
                           unmatched_reply):
    try:
        if not isinstance(body, dict):
            raise ValueError("Send an intent correction or removal.")
        if (set(body) == {"forget"} and isinstance(body["forget"], str)
                and 0 < len(body["forget"]) <= 120):
            forget_intent(body["forget"])
        elif set(body) == {"phrase", "target", "previous"}:
            edit_intent(body["phrase"], body["target"], body["previous"])
        elif (set(body) == {"turn_id", "target"} and type(body["turn_id"]) is int
              and 0 < body["turn_id"] < 2**63 and isinstance(body["target"], str)
              and 0 < len(body["target"]) <= 120):
            teach_intent(body["turn_id"], body["target"], unmatched_reply)
        else:
            raise ValueError("Choose a missed voice command and enter what you meant.")
    except ValueError as error:
        handler.send_json(400, {"error": str(error)})
        return
    except (OSError, sqlite3.Error):
        handler.send_json(503, {"error": "Intent corrections are unavailable."})
        return
    handler.send_json(200, {"saved": True})
