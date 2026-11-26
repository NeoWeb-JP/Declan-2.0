"""Small Home Assistant REST helpers for the household questions (FUT-29 to FUT-41).

``connection`` is the usual ``(url, headers, opener)`` tuple from
``services.ha_device_connection()``. Every read is bounded in size and time.
"""
import json
from urllib.error import HTTPError
from urllib.request import Request
from declan.ha import ha_replies

MAX_BYTES = 262144


def call(connection, path, data=None, *, timeout=8):
    """POST ``data`` (or GET when None) and return the decoded JSON."""
    url, headers, opener = connection
    body = None if data is None else json.dumps(data).encode()
    request = Request(url + path, data=body, headers={**headers, "Content-Type": "application/json"},
                      method="GET" if data is None else "POST")
    try:
        with opener.open(request, timeout=timeout) as response:
            return ha_replies.decode(response, path, MAX_BYTES)
    except HTTPError as error:
        error.close()
        raise OSError(f"Home Assistant returned {error.code}") from None


def template(connection, text, *, timeout=8):
    """Render a Jinja template in Home Assistant; the template must end in ``| to_json``."""
    return call(connection, "/api/template", {"template": text}, timeout=timeout)


def guest(services):
    """True when Guest Mode is on, or when it can't be read (private answers stay private)."""
    try:
        return services.read_guest_mode() != "off"
    except (OSError, ValueError, TypeError, AttributeError):
        return True
