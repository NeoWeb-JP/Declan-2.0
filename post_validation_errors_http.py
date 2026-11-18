"""Preserve route-specific HTTP 400 errors for malformed POST payloads."""


def validation_error_message(path):
    if path == "/api/settings/spotify":
        return "Send valid Spotify settings."
    if path == "/api/history/clear":
        return "Send valid history confirmation."
    return "Send a message of 1 to 1,000 characters."


def send_validation_error(handler):
    handler.send_json(400, {"error": validation_error_message(handler.path)})
