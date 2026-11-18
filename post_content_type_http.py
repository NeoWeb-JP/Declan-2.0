"""POST JSON content-type boundary, separate from browser audio upload."""


def enforce_json_content_type(handler):
    """Retain existing MIME parsing and 415 response for JSON POST routes."""
    if handler.headers.get_content_type() != "application/json":
        handler.send_json(415, {"error": "Send application/json."})
        return False
    return True
