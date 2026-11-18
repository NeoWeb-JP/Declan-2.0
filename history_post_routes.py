"""Authorised history-clear POST response adapter.

Request origin, authentication, size limits and JSON decoding remain in server.py.
"""


def handle_history_clear(handler, body, *, clear, storage_errors):
    if not isinstance(body, dict) or body.get("confirm") is not True:
        handler.send_json(400, {"error": "Confirm before clearing conversation history."})
        return
    try:
        deleted = clear()
    except storage_errors:
        handler.send_json(503, {"error": "Conversation history could not be cleared."})
        return
    handler.send_json(200, {"deleted": deleted})
