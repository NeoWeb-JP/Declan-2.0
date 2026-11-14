"""Parse server capability metadata without coupling component release versions.

This module deliberately performs no network calls. The HA integration can use
it when its authenticated backend connection supplies /api/capabilities data.
"""
from dataclasses import dataclass
from typing import Any, Mapping


SUPPORTED_API_MAJOR = 1


@dataclass(frozen=True)
class ServerCompatibility:
    compatible: bool
    server_version: str | None
    api_version: str | None
    reason: str


def check_server_compatibility(payload: Mapping[str, Any]) -> ServerCompatibility:
    """Fail closed on missing, malformed or unsupported API version metadata."""
    server = payload.get("server_version")
    api = payload.get("api_version")
    server_version = server if isinstance(server, str) and server.strip() else None
    api_version = api if isinstance(api, str) and api.strip() else None
    if api_version is None:
        return ServerCompatibility(False, server_version, None, "API version not advertised")
    major, separator, minor = api_version.partition(".")
    if not major.isdecimal() or (separator and (not minor or not all(part.isdecimal() for part in minor.split(".")))):
        return ServerCompatibility(False, server_version, api_version, "Invalid API version")
    if int(major) != SUPPORTED_API_MAJOR:
        return ServerCompatibility(False, server_version, api_version, "Unsupported API major version")
    return ServerCompatibility(True, server_version, api_version, "Compatible")
