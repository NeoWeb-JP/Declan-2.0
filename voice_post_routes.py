"""HTTP POST route adapters for VoicePipeline and voice-profile management.

Access control, body parsing and size checks remain in the HTTP handler.
Only the already-authorised route-specific response mapping lives here.
"""

import sqlite3


def handle_voicepipeline(handler, body, *, manage, pipeline_error):
    try:
        handler.send_json(200, manage(body))
    except pipeline_error as error:
        handler.send_json(error.status, {"error": str(error)})
    except ValueError as error:
        handler.send_json(400, {"error": str(error)})


def handle_voice_profiles(handler, body, *, manage):
    try:
        if isinstance(body, dict) and body.get("operation") in {"create", "save_sample"}:
            raise ValueError(
                "Use Voice profiles to enrol through VoicePipeline. "
                "Separate local collection is retired."
            )
        handler.send_json(200, manage(body))
    except ValueError as error:
        handler.send_json(400, {"error": str(error)})
    except (OSError, sqlite3.Error):
        handler.send_json(503, {"error": "Voice profiles could not be saved."})
