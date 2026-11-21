"""Clear failure responses (FUT-24, #834).

When a request fails with "unavailable" or "failed", Declan checks what is
actually down before saying so:

- Home Assistant not answering (or rejecting Declan's token): nothing in the
  house can work, so he says exactly that.
- Music Assistant players all unavailable, for a music failure: music is down,
  the lights still work.
- Otherwise the original, specific reply stands (a device being unavailable, a
  request that wasn't understood, an action that couldn't be verified, or one
  that needs permission all already have their own replies).

A service is only blamed after a successful check shows it's down; a check
that can't run blames nothing. Checks are cached for 30 seconds so a burst of
failures costs one probe.
"""
import json
import re
import threading
from time import monotonic
from urllib.error import HTTPError
from urllib.request import Request

CACHE_SECONDS = 30
_CACHE: dict[str, tuple[float, str]] = {}
_LOCK = threading.Lock()
_MUSIC_WORDS = re.compile(r"\b(?:music|spotify|song|playlist|track|radio|music assistant|playback|speaker|queue|volume)\b",
                          re.IGNORECASE)

HA_DOWN = ("Home Assistant isn't answering, boet, so nothing in the house will work until it's back. "
           "It's not you, it's the server.")
HA_AUTH = "Home Assistant won't let me in. My access token's been rejected, so check it in Declan's settings."
MUSIC_DOWN = "Music Assistant's having a tantrum, my bru. The speakers aren't answering, but your lights still work."


def _cached(key, check, now):
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and now - hit[0] < CACHE_SECONDS:
            return hit[1]
    value = check()
    with _LOCK:
        _CACHE[key] = (now, value)
    return value


def ha_state(connection):
    """"up", "down", "auth" or "unknown" (the check itself couldn't run)."""
    if connection is None:
        return "unknown"
    url, headers, opener = connection
    try:
        with opener.open(Request(url + "/api/", headers=headers), timeout=3) as response:
            payload = json.loads(response.read(4096))
        return "up" if payload == {"message": "API running."} else "down"
    except HTTPError as error:
        code = error.code
        error.close()
        return "auth" if code in {401, 403} else "down"
    except (TimeoutError, ConnectionError):
        return "down"
    except OSError as error:
        # URLError wraps refused/unreachable connections: that is HA being down.
        return "down" if "refused" in str(error).lower() or "unreachable" in str(error).lower() \
            or "timed out" in str(error).lower() else "unknown"
    except ValueError:
        return "unknown"


def music_state(connection):
    """"up", "down" (every Music Assistant player unavailable) or "unknown"."""
    if connection is None:
        return "unknown"
    url, headers, opener = connection
    template = ("{{ integration_entities('music_assistant') | select('match', '^media_player[.]') "
                "| map('states') | list | to_json }}")
    try:
        request = Request(url + "/api/template", data=json.dumps({"template": template}).encode(),
                          headers=headers, method="POST")
        with opener.open(request, timeout=3) as response:
            states = json.loads(response.read(65536))
    except HTTPError as error:
        error.close()
        return "unknown"
    except (OSError, ValueError):
        return "unknown"
    if not isinstance(states, list) or not states:
        return "unknown"
    return "down" if all(state in {"unavailable", "unknown"} for state in states) else "up"


def explain(reply, connection, *, now=None):
    """A clearer reply for a failure, or None to keep the original."""
    now = monotonic() if now is None else now
    ha = _cached("ha", lambda: ha_state(connection), now)
    if ha == "down":
        return HA_DOWN
    if ha == "auth":
        return HA_AUTH
    music_failure = ha == "up" and isinstance(reply, str) and bool(_MUSIC_WORDS.search(reply))
    if music_failure and _cached("music", lambda: music_state(connection), now) == "down":
        return MUSIC_DOWN
    return None


def clear_cache():
    with _LOCK:
        _CACHE.clear()
