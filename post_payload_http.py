"""Bounded JSON request parsing for Declan POST endpoints."""

import json


def max_json_body_bytes(path):
    """Preserve endpoint-specific request size limits."""
    if path == "/api/native/routine-responses":
        return 131072
    if path == "/api/voice-profiles":
        return 450000
    if path == "/api/settings/import":
        return 196608
    if path in {"/api/assist/history", "/api/assist", "/api/chat"}:
        return 65536
    return 8192


def read_json_body(handler):
    """Parse one bounded JSON request; caller retains existing error mapping."""
    size = int(handler.headers.get("Content-Length", "0"))
    if not 0 < size <= max_json_body_bytes(handler.path):
        raise ValueError("Invalid request body size")
    return json.loads(handler.rfile.read(size))
