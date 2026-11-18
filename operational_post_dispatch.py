"""Operational POST routing around shared request validation."""
import operational_post_routes
import speech_http_routes


def handles_pre_validation(path):
    return path == "/api/updates"


def handles_after_validation(path):
    return path in {"/api/tts", "/api/assist/history"}


def dispatch_update(handler, body, *, check, status_result,
                    prerelease_versions, queue, release_version):
    if not handles_pre_validation(handler.path):
        raise ValueError("Unsupported operational update POST route")
    operational_post_routes.handle_updates(
        handler, body, check=check, status_result=status_result,
        prerelease_versions=prerelease_versions, queue=queue,
        release_version=release_version,
    )


def dispatch_validated(handler, body, *, message, session_id, render,
                       record, token_urlsafe, action_results):
    if handler.path == "/api/tts":
        speech_http_routes.render_tts(handler, message, render=render)
    elif handler.path == "/api/assist/history":
        operational_post_routes.handle_assist_history(
            handler, body, message=message, session_id=session_id,
            record=record, token_urlsafe=token_urlsafe,
            action_results=action_results,
        )
    else:
        raise ValueError("Unsupported validated operational POST route")
