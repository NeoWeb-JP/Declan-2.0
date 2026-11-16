"""Discover and run Home Assistant scripts without per-script approval."""
import json
import re
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
    # "Declan - Sexy Time Controller" should respond to "sexy time".
    for alias in tuple(result):
        if alias.endswith(" controller"):
            result.add(alias.removesuffix(" controller"))
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
    # Never guess between multiple scripts with the same spoken name.
    if len(matches) != 1:
        return "ambiguous", matches
    item = matches[0]
    return "matched", item


def execute(connection, item, *, parameters=None):
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
    request = Request(url + "/api/services/script/turn_on",
                      headers=headers, method="POST",
                      data=json.dumps(payload).encode())
    try:
        with opener.open(request, timeout=15) as response:
            if response.status not in (200, 201):
                return "Home Assistant didn't accept the script request.", "unverified", None
            response.read(8192)
    except (OSError, HTTPError):
        return "Home Assistant didn't confirm the script request.", "unverified", None
    return f"Started {current['name']}.", "requested", None
