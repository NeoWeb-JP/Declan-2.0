"""Trusted HA dispatcher with bounded post-action state verification."""
import json
from time import monotonic, sleep
from urllib.error import HTTPError
from urllib.request import Request

from declan.ai.action_plan import CandidateAction, SERVICES
from declan.core.execution_results import ActionStatus, DispatchResult

EXPECTED = {
    "turn_on": "on", "turn_off": "off", "open_cover": "open",
    "close_cover": "closed", "media_pause": "paused",
    "media_play": "playing", "media_stop": "idle",
}
# A TV that has just been switched on may report any active state.
ACCEPTED = {
    ("media_player", "turn_on"): frozenset({"on", "idle", "playing", "paused", "buffering"}),
    ("media_player", "turn_off"): frozenset({"off", "standby"}),
}


def dispatch_result(action, connection, *, authorised, clock=monotonic, wait=sleep):
    """Never treat HTTP acknowledgement as confirmed device state.

    The caller must enforce owner permissions and sensitive confirmations in
    the authorised callback, including a fresh entity exposure check.
    """
    if not isinstance(action, CandidateAction):
        raise ValueError("Unvalidated action")
    if not callable(authorised) or not authorised(action):
        return DispatchResult(ActionStatus.FAILED, "Action not authorised")
    if not isinstance(connection, tuple) or len(connection) != 3:
        raise ValueError("Invalid HA connection")
    base_url, headers, opener = connection
    if (not isinstance(base_url, str) or not base_url.startswith(("http://", "https://"))
            or not isinstance(headers, dict) or not hasattr(opener, "open")):
        raise ValueError("Invalid HA connection")
    domain, _, object_id = action.entity_id.partition(".")
    if not object_id or domain not in SERVICES or action.service not in SERVICES[domain]:
        return DispatchResult(ActionStatus.FAILED, "Unsupported service")
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
        return DispatchResult(ActionStatus.FAILED, f"Home Assistant rejected request (HTTP {code})")
    except OSError:
        return DispatchResult(ActionStatus.UNVERIFIED, "No dispatch acknowledgement")
    if domain == "script":
        return DispatchResult(ActionStatus.UNVERIFIED, "Script started; completion not verified")
    expected = EXPECTED[action.service]
    accepted = ACCEPTED.get((domain, action.service), frozenset({expected}))
    deadline = clock() + 3.0
    while True:
        try:
            read = Request(f"{url}/api/states/{action.entity_id}", headers=headers)
            with opener.open(read, timeout=1.5) as response:
                raw = response.read(65537)
            if len(raw) > 65536:
                return DispatchResult(ActionStatus.UNVERIFIED, "State response too large")
            observed = json.loads(raw).get("state")
            if observed in accepted:
                return DispatchResult(ActionStatus.CONFIRMED, f"Observed {observed}")
            if observed in ("unknown", "unavailable"):
                return DispatchResult(ActionStatus.UNVERIFIED, "Entity state unavailable")
        except HTTPError as error:
            error.close()
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        remaining = deadline - clock()
        if remaining <= 0:
            return DispatchResult(ActionStatus.UNVERIFIED, f"Expected {expected}; state not confirmed")
        wait(min(0.25, remaining))


def dispatch_verified(action, connection, *, authorised, clock=monotonic, wait=sleep):
    """Compatibility API: keep the legacy (status-string, detail) tuple."""
    return dispatch_result(action, connection, authorised=authorised,
                           clock=clock, wait=wait).as_legacy_pair()
