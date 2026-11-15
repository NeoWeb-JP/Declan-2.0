"""Trusted HA dispatcher with bounded post-action state verification."""
import json
from time import monotonic, sleep
from urllib.error import HTTPError
from urllib.request import Request

from action_plan import CandidateAction

EXPECTED = {
    "turn_on": "on", "turn_off": "off", "open_cover": "open",
    "close_cover": "closed", "media_pause": "paused",
    "media_play": "playing", "media_stop": "idle",
}
SERVICES = {
    "light": {"turn_on", "turn_off"}, "switch": {"turn_on", "turn_off"},
    "fan": {"turn_on", "turn_off"}, "cover": {"open_cover", "close_cover"},
    "script": {"turn_on"}, "media_player": {"media_pause", "media_play", "media_stop"},
}


def dispatch_verified(action, connection, *, authorised, clock=monotonic, wait=sleep):
    """Never treat HTTP acknowledgement as confirmed device state.

    The caller must enforce owner permissions and sensitive confirmations in
    the authorised callback, including a fresh entity exposure check.
    """
    if not isinstance(action, CandidateAction):
        raise ValueError("Unvalidated action")
    if not callable(authorised) or not authorised(action):
        return "failed", "Action not authorised"
    if not isinstance(connection, tuple) or len(connection) != 3:
        raise ValueError("Invalid HA connection")
    base_url, headers, opener = connection
    if (not isinstance(base_url, str) or not base_url.startswith(("http://", "https://"))
            or not isinstance(headers, dict) or not hasattr(opener, "open")):
        raise ValueError("Invalid HA connection")
    domain, _, object_id = action.entity_id.partition(".")
    if not object_id or domain not in SERVICES or action.service not in SERVICES[domain]:
        return "failed", "Unsupported service"
    url = base_url.rstrip("/")
    request = Request(f"{url}/api/services/{domain}/{action.service}",
                      headers=headers, data=json.dumps({"entity_id": action.entity_id}).encode(),
                      method="POST")
    try:
        with opener.open(request, timeout=1.5) as response:
            response.read(65537)
    except HTTPError as error:
        code = error.code
        error.close()
        return "failed", f"Home Assistant rejected request (HTTP {code})"
    except OSError:
        return "unverified", "No dispatch acknowledgement"
    if domain == "script":
        return "unverified", "Script started; completion not verified"
    expected = EXPECTED[action.service]
    deadline = clock() + 3.0
    while True:
        try:
            read = Request(f"{url}/api/states/{action.entity_id}", headers=headers)
            with opener.open(read, timeout=1.5) as response:
                raw = response.read(65537)
            if len(raw) > 65536:
                return "unverified", "State response too large"
            observed = json.loads(raw).get("state")
            if observed == expected:
                return "confirmed", f"Observed {expected}"
            if observed in ("unknown", "unavailable"):
                return "unverified", "Entity state unavailable"
        except HTTPError as error:
            error.close()
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        remaining = deadline - clock()
        if remaining <= 0:
            return "unverified", f"Expected {expected}; state not confirmed"
        wait(min(0.25, remaining))
