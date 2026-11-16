"""Discover and run Home Assistant scripts without per-script approval."""
import json
import re
import secrets
from threading import Lock
from time import monotonic
from urllib.error import HTTPError
from urllib.request import Request

_CACHE = {}
_CACHE_LOCK = Lock()
CACHE_SECONDS = 30


def normalise(value):
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", value.casefold()).split())


def phrases(item):
    name = normalise(item["name"])
    entity = normalise(item["entity_id"].removeprefix("script.").replace("_", " "))
    result = {name, entity}
    # Home Assistant script labels commonly include the assistant name.
    # Spoken "good night" should match "Declan - Good Night" without
    # requiring a separate Declan-side alias or routine mapping.
    for prefix in ("declan ", "declan local ", "declan 2 "):
        if name.startswith(prefix):
            result.add(name[len(prefix):])
        if entity.startswith(prefix):
            result.add(entity[len(prefix):])
    # A Home Assistant script may have a descriptive implementation suffix,
    # e.g. "Declan - Good Morning - Shared Local Routine". Resolve the short
    # spoken name to the real registered script rather than an obsolete alias.
    for alias in tuple(result):
        for suffix in (" shared local routine", " local routine"):
            if alias.endswith(suffix):
                result.add(alias.removesuffix(suffix))
    # "Declan - Sexy Time Controller" should respond to "sexy time".
    for alias in tuple(result):
        if alias.endswith(" controller"):
            result.add(alias.removesuffix(" controller"))
        # HA appends numeric suffixes when a script entity is duplicated.
        # The full name remains authoritative; an ambiguous alias is never
        # selected automatically when more than one script shares it.
        numbered = re.fullmatch(r"(.+?) [0-9]+", alias)
        if numbered:
            result.add(numbered[1])
    if name.endswith(" status"):
        result.update({"what is the " + name, "what is the status of the " + name.removesuffix(" status"),
                       "give me the " + name})
    return result


def discover(connection, *, fresh=False):
    if connection is None:
        return [], "not_connected"
    url, headers, opener = connection
    if opener is None or not hasattr(opener, "open"):
        return [], "inspection_unavailable"
    if not fresh:
        with _CACHE_LOCK:
            cached = _CACHE.get(url)
            if cached and monotonic() - cached[0] < CACHE_SECONDS:
                return cached[1], None
    try:
        with opener.open(Request(url + "/api/declan_two/script-discovery", headers=headers), timeout=5) as response:
            payload = json.loads(response.read(512 * 1024))
        if not isinstance(payload, dict) or payload.get("inspection") != "complete":
            return [], "inspection_unavailable"
        rows = payload.get("scripts")
        if not isinstance(rows, list) or len(rows) > 20000:
            return [], "invalid"
        valid = []
        for item in rows:
            if (isinstance(item, dict) and isinstance(item.get("name"), str)
                    and 0 < len(item["name"]) <= 120 and
                    isinstance(item.get("entity_id"), str) and
                    re.fullmatch(r"script\.[a-z0-9_]+", item["entity_id"]) and
                    type(item.get("safe")) is bool):
                valid.append(item)
        if len(valid) != len(rows):
            return [], "invalid"
        with _CACHE_LOCK:
            _CACHE[url] = (monotonic(), valid)
        return valid, None
    except (OSError, ValueError, TypeError, HTTPError):
        return [], "inspection_unavailable"


def match(phrase, scripts):
    phrase = normalise(phrase)
    phrase = re.sub(r"^(?:please |run |start |execute |activate )", "", phrase)
    matches = [item for item in scripts if phrase in phrases(item)]
    if not matches:
        return None
    # Prefer the one HA script explicitly designed to return Declan's
    # correlated completion result. Other similarly named scripts may be
    # legacy wrappers or duplicates. This is capability-based, not a
    # hardcoded script entity ID. Never guess when multiple candidates qualify.
    if len(matches) > 1:
        response_capable = [
            item for item in matches
            if isinstance(item.get("fields"), list)
            and {"request_id", "routine_id"}.issubset(item["fields"])
        ]
        if len(response_capable) == 1:
            return "matched", response_capable[0]
        return "ambiguous", matches
    item = matches[0]
    return "matched", item


def execute(connection, item, *, parameters=None, expect_response=False):
    """Verify the live HA script and send only parameters it declares."""
    scripts, error = discover(connection, fresh=True)
    if error:
        return "I couldn't verify that script exists in Home Assistant. Nothing was run.", "unverified", None
    current = next((row for row in scripts if row["entity_id"] == item["entity_id"]), None)
    if not current:
        return "That script is no longer available in Home Assistant.", "unresolved", None
    url, headers, opener = connection
    allowed_fields = current.get("fields", [])
    if not isinstance(allowed_fields, list):
        allowed_fields = []
    supplied = {key: value for key, value in (parameters or {}).items()
                if key in allowed_fields and isinstance(value, (str, int, float, bool))}
    payload = {"entity_id": current["entity_id"]}
    if supplied:
        payload["variables"] = supplied

    # Execute the script service itself. script.turn_on only confirms scheduling.
    service = current["entity_id"].split(".", 1)[1]
    request_id = "declan-" + secrets.token_hex(16)
    if "request_id" in allowed_fields:
        supplied["request_id"] = request_id
    if "routine_id" in allowed_fields:
        supplied["routine_id"] = current["entity_id"]
    request = Request(url + "/api/services/script/" + service + "?return_response",
                      headers=headers, method="POST",
                      data=json.dumps(supplied).encode())
    try:
        with opener.open(request, timeout=55) as response:
            if response.status not in (200, 201):
                return "Home Assistant did not confirm script execution.", "unverified", None
            result = json.loads(response.read(65536))
    except HTTPError as error:
        code = error.code
        # Preserve HA's useful validation reason. Never log tokens or headers.
        try:
            body = error.read(4096).decode("utf-8", errors="replace")
        except (OSError, ValueError):
            body = ""
        finally:
            error.close()
        try:
            parsed = json.loads(body)
            reason = parsed.get("message", "") if isinstance(parsed, dict) else ""
        except ValueError:
            reason = body
        reason = re.sub(r"[\r\n\t]+", " ", str(reason)).strip()[:240]
        # Some HA versions reject return_response for a script service that
        # does not advertise response support. Retry ONLY when HA explicitly
        # states this, never for an arbitrary 400 (which could be bad data).
        unsupported_response = (
            code == 400 and "response" in reason.casefold()
            and any(term in reason.casefold() for term in
                    ("does not support", "doesn't support", "not supported", "unsupported"))
        )
        if unsupported_response:
            plain_request = Request(url + "/api/services/script/" + service,
                                    headers=headers, method="POST",
                                    data=json.dumps(supplied).encode())
            try:
                with opener.open(plain_request, timeout=55) as response:
                    if response.status not in (200, 201):
                        return "Home Assistant did not confirm script dispatch.", "unverified", None
                    response.read(8192)
            except HTTPError as retry_error:
                retry_code = retry_error.code
                retry_error.close()
                return f"Home Assistant rejected script execution (HTTP {retry_code}).", "failed", None
            except OSError:
                return "Home Assistant could not confirm script execution.", "unverified", None
            return (current["name"] + " was sent to Home Assistant, but this script service "
                    "does not support returning a completion result. Check the script trace.",
                    "unverified", None)
        return (f"Home Assistant rejected the script (HTTP {code})"
                + (f": {reason}" if reason else "."),
                "failed", None)
    except (OSError, ValueError, TypeError):
        return "Home Assistant did not return a valid script result. Check its trace.", "unverified", None
    data = result.get("service_response") if isinstance(result, dict) else None
    if isinstance(data, dict) and current["entity_id"] in data:
        data = data[current["entity_id"]]
    if not isinstance(data, dict):
        return "Home Assistant returned no script result. Check response_variable and traces.", "unverified", None
    if "outcome" in data:
        if "request_id" in allowed_fields and data.get("request_id") != request_id:
            return "Script result did not match this request.", "unverified", None
        if "routine_id" in allowed_fields and data.get("routine_id") != current["entity_id"]:
            return "Script result did not match this routine.", "unverified", None
        outcome = str(data["outcome"]).lower()
        statuses = {"success": "reported_success", "partial": "partial",
                    "failed": "failed", "cancelled": "cancelled",
                    "unknown": "unverified", "started": "started"}
        if outcome not in statuses:
            return "Home Assistant returned an unknown script outcome.", "unverified", None
        steps = data.get("steps", [])
        if outcome == "success" and isinstance(steps, list):
            if any(isinstance(step, dict) and step.get("required", True)
                   and step.get("status") not in {"confirmed", "already_set"}
                   for step in steps):
                return "Script success was not confirmed by its required steps.", "unverified", None
        description = {"success": "completed successfully", "partial": "partially completed",
                       "failed": "failed", "cancelled": "was cancelled",
                       "unknown": "could not be verified", "started": "started but not completed"}[outcome]
        return current["name"] + " " + description + ".", statuses[outcome], None
    for key in ("speech", "reply", "message", "response", "summary"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:4000], "reported_success", None
    return "Home Assistant returned no completion status or spoken summary.", "unverified", None
