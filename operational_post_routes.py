"""POST adapters for authorised update, Spotify credential and Assist history requests.

HTTP authentication, origin checks, content-type and size limits stay in server.py.
"""

import sqlite3
import subprocess  # nosec B404 - only catches errors from controlled update operations


def handle_updates(handler, body, *, check, status_result, prerelease_versions,
                   queue, release_version):
    try:
        if isinstance(body, dict) and body.get("operation") == "check":
            versions = check(body.get("include_prereleases", False))
            handler.send_json(200, {
                **status_result().to_wire(), "current": release_version,
                "versions": versions, "prereleases": prerelease_versions(),
            })
            return
        queue(
            body.get("version") if isinstance(body, dict) else None,
            release_version,
            body.get("include_prereleases", False) if isinstance(body, dict) else False,
        )
    except ValueError as error:
        handler.send_json(409, {"error": str(error)})
        return
    except (OSError, subprocess.SubprocessError):
        handler.send_json(503, {"error": "Couldn't check GitHub for releases."})
        return
    handler.send_json(202, {"status": "installing"})


def handle_spotify_credentials(handler, body, *, save):
    if (not isinstance(body, dict) or set(body) != {"client_id", "client_secret", "confirm"}
            or body.get("confirm") is not True):
        handler.send_json(400, {
            "error": "Explicit confirmation and both credentials required.",
        })
        return
    save(body)


def handle_assist_history(handler, body, *, message, session_id, record,
                          token_urlsafe, action_results):
    spoken_reply = body.get("reply")
    if not isinstance(spoken_reply, str) or not 0 < len(spoken_reply.strip()) <= 1000:
        handler.send_json(400, {"error": "A reply of 1 to 1,000 characters is required."})
        return
    try:
        outcome = body.get("outcome")
        routine_status = body.get("routine_status")
        record(
            session_id or token_urlsafe(24), "ha_sentence", message, spoken_reply,
            outcome if isinstance(outcome, str) and len(outcome) <= 64 else None,
            routine_status if isinstance(routine_status, str) and len(routine_status) <= 1000 else None,
            action_results(body.get("steps")),
        )
    except (OSError, sqlite3.Error):
        handler.send_json(503, {"error": "Conversation history is unavailable."})
        return
    handler.send_json(200, {"history_saved": True})
