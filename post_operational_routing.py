"""Operational POST route boundary, before and after message validation."""

import operational_post_dispatch


def dispatch_before_validation(handler, body, *, updates, release_version):
    """Handle updater POST without requiring a conversation message."""
    if not operational_post_dispatch.handles_pre_validation(handler.path):
        return False
    operational_post_dispatch.dispatch_update(
        handler, body, check=updates.check,
        status_result=updates.status_result,
        prerelease_versions=updates.prerelease_versions,
        queue=updates.queue, release_version=release_version,
    )
    return True


def dispatch_after_validation(handler, body, *, message, session_id,
                              render, record, token_urlsafe, action_results):
    """Handle validated operational POST before starting a conversation turn."""
    if not operational_post_dispatch.handles_after_validation(handler.path):
        return False
    operational_post_dispatch.dispatch_validated(
        handler, body, message=message, session_id=session_id,
        render=render, record=record,
        token_urlsafe=token_urlsafe, action_results=action_results,
    )
    return True
