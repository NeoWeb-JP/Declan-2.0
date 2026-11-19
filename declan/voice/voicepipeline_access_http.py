"""Restrict VoicePipeline Assist-token POST operations to the existing safe subset."""


def requires_local_access(*, path, ingress, client_ip, body):
    """Preserve the local-only boundary for destructive VoicePipeline operations."""
    if path != "/api/voicepipeline" or ingress or client_ip == "127.0.0.1":
        return False
    if not isinstance(body, dict):
        return True
    operation = body.get("operation")
    if operation not in {"resolve", "audio", "history", "correct"}:
        return True
    if operation == "resolve":
        return body.get("action") not in {"confirm", "assign", "dismiss", "enrol"}
    if operation == "audio":
        return set(body) != {"operation", "interaction_id"}
    if operation == "history":
        return set(body) != {"operation"}
    return (
        set(body) != {"operation", "interaction_id", "assigned_to", "expected_resolution_id", "confirm"}
        or body.get("confirm") is not True
    )


def enforce_access(handler, body, *, ingress):
    if requires_local_access(
        path=handler.path, ingress=ingress, client_ip=handler.client_address[0], body=body,
    ):
        handler.send_json(403, {"error": "This VoicePipeline action requires local access."})
        return False
    return True
