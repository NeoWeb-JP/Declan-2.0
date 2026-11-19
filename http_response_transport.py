"""HTTP response transport shared by Declan request handlers.

Keep diagnostics, privacy-safe route logging, response headers and byte writes
in one place; callers retain the existing handler methods.
"""

import json
import os
from urllib.parse import urlsplit

import diagnostics
from declan_ingress.security import secure_page


_LOGGED_POST_ROUTES = frozenset({
    "/api/assist", "/api/chat", "/api/settings/music-playlists",
    "/api/settings/media-players", "/api/updates/install",
})


def send_body(handler, status, data, content_type, *, filename=None, logger):
    handler._page_nonce = None
    if content_type.startswith("text/html"):
        data, handler._page_nonce = secure_page(data)
    trace = diagnostics.ACTIVE.get()
    if trace is not None:
        if diagnostics.outcome_result(trace).status is diagnostics.DiagnosticOutcome.UNKNOWN:
            diagnostics.set_outcome(
                trace,
                diagnostics.DiagnosticOutcome.FAILED
                if status >= 400 else diagnostics.DiagnosticOutcome.COMPLETED,
            )
        diagnostics.persist(trace)
    route = urlsplit(handler.path).path
    if status >= 400:
        logger.warning("HTTP %d %s %s", status, handler.command, route)
    elif handler.command == "POST" and route in _LOGGED_POST_ROUTES:
        logger.info("HTTP %d POST %s", status, route)
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", "no-store")
    if handler.path == "/health":
        handler.send_header("X-Declan-Pid", str(os.getpid()))
    if filename:
        handler.send_header("Content-Disposition", f'attachment; filename="{filename}"')
    handler.end_headers()
    handler.wfile.write(data)


def send_json(handler, status, data, *, logger):
    trace = diagnostics.ACTIVE.get()
    if trace is not None:
        diagnostics.set_outcome(
            trace,
            data.get("outcome") or (
                diagnostics.DiagnosticOutcome.FAILED
                if status >= 400 else diagnostics.DiagnosticOutcome.COMPLETED
            ),
        )
        data = {**data, "diagnostic_id": trace["id"]}
    send_body(handler, status, json.dumps(data).encode(), "application/json", logger=logger)
