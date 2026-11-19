"""HA ingress authentication and HTTP security header boundary."""

import os
import secrets

from declan_ingress.security import response_headers


def has_ingress_access(handler):
    """Only accept a dedicated configured ingress token, never the Assist token."""
    token = os.environ.get("DECLAN_INGRESS_TOKEN", "")
    supplied = handler.headers.get("X-Declan-Ingress-Token", "")
    return (
        len(token) >= 32
        and token != os.environ.get("DECLAN_ASSIST_TOKEN", "")
        and secrets.compare_digest(supplied.encode(), token.encode())
    )


def send_security_headers(handler):
    """Retain the existing per-response nonce and HA ingress security headers."""
    ingress = hasattr(handler, "headers") and handler.has_ingress_access()
    for name, value in response_headers(
        ingress=ingress, nonce=getattr(handler, "_page_nonce", None),
    ).items():
        handler.send_header(name, value)
