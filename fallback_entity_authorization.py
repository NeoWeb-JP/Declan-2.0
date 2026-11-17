"""Authorize HA-exposed entities for guarded AI fallback requests."""
import secrets


def exposed_entities(body, authorization, bridge_token):
    """Only forward exposed entities for a matching, sufficiently long HA token."""
    authenticated_ha = len(bridge_token) >= 32 and secrets.compare_digest(
        authorization.encode(), ("Bearer " + bridge_token).encode()
    )
    return body.get("ai_exposed_entities", ()) if authenticated_ha else ()
