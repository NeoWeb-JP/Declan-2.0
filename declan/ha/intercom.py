"""One-way intercom and broadcast (FUT-25, #834).

"Tell the kitchen dinner's ready", "announce to everyone: leaving in five
minutes", "announce upstairs: bedtime". The message is spoken on the Assist
satellites in that room (or every satellite, or the ones on an upstairs or
downstairs floor in Home Assistant) through assist_satellite.announce, starting
with where it came from: "Message from the lounge: dinner's ready."

- "Everyone" skips the satellite that heard the request.
- During quiet hours (23:00-07:00) Declan won't announce in other rooms.
- A satellite that can't be reached is reported, never hidden.
Two-way replies are FUT-34.
"""
import json
import re
from urllib.error import HTTPError
from urllib.request import Request

from declan.core.execution_results import ExecutionResult, Outcome

_ALL = {"everyone", "everybody", "everywhere", "the house", "the whole house", "all rooms", "all the rooms"}
_ANNOUNCE = re.compile(r"(?:announce|broadcast|shout)(?: (?:to|in|on|for) (?:the )?(?P<target>[a-z][a-z' ]{1,40}?)| (?P<floor>upstairs|downstairs))?"
                       r"(?:,|:| that| -)? (?P<message>.+)")
_TELL = re.compile(r"(?:tell|let) (?:the )?(?P<rest>[a-z].+)")
_SATELLITES_TEMPLATE = (
    "{% set ns = namespace(rows=[]) %}"
    "{% for entity in states.assist_satellite %}"
    "{% set area = area_name(entity.entity_id) %}"
    "{% set ns.rows = ns.rows + [[entity.entity_id, area or '', "
    "(floor_name(area_id(entity.entity_id)) if area_id(entity.entity_id) else '') or '', entity.state, "
    "device_id(entity.entity_id) or '']] %}"
    "{% endfor %}{{ ns.rows | to_json }}"
)


def match(phrase):
    """("announce", target or None, message) | ("tell", rest) or None. Rooms are resolved against HA later."""
    if not isinstance(phrase, str):
        return None
    text = " ".join(phrase.replace("’", "'").split()).strip(" .!")
    lowered = text.casefold()
    if found := _ANNOUNCE.fullmatch(lowered):
        if found["target"]:
            # Rooms can be several words ("master bedroom"): match them against HA later.
            start = found.start("target")
            return ("tell", text[start:]) if found["target"].strip() not in {"that", "this"} else None
        message = text[found.start("message"):].strip(" ,:-")
        # "announce dinner" is the Dinner routine; a broadcast needs a real message.
        if not message or (not found["floor"] and len(message.split()) < 2):
            return None
        return ("announce", found["floor"], message)
    if found := _TELL.fullmatch(lowered):
        return ("tell", text[found.start("rest"):])
    return None


def _call(connection, path, data):
    url, headers, opener = connection
    request = Request(url + path, data=json.dumps(data).encode(), headers=headers, method="POST")
    with opener.open(request, timeout=8) as response:
        return json.loads(response.read(262144) or b"null")


def satellites(connection):
    rows = _call(connection, "/api/template", {"template": _SATELLITES_TEMPLATE})
    if not isinstance(rows, list):
        return []
    return [{"entity_id": row[0], "area": row[1], "floor": row[2], "state": row[3], "device": row[4]}
            for row in rows if isinstance(row, list) and len(row) == 5 and all(isinstance(value, str) for value in row)]


def _norm(text):
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", text.casefold()).split()).removeprefix("the ")


def resolve(request, rows):
    """(target label, [satellite rows], message), or an error reply."""
    areas = sorted({row["area"] for row in rows if row["area"]}, key=len, reverse=True)
    if request[0] == "tell":
        rest = request[1]
        lowered = _norm(rest)
        for target in [*sorted(_ALL, key=len, reverse=True), *[_norm(area) for area in areas]]:
            if lowered.startswith(_norm(target) + " "):
                words = len(_norm(target).split())
                original = re.sub(r"^the ", "", rest, flags=re.IGNORECASE).split(" ", words)
                message = original[-1] if len(original) > words else ""
                message = re.sub(r"^[,:\-]?\s*(?:that |to )?", "", message, flags=re.IGNORECASE)
                request = ("announce", target, message)
                break
        else:
            return None  # "tell me a joke": not an intercom request
    _, target, message = request
    if not message:
        return "What should I say?"
    target_norm = _norm(target) if target else "everyone"
    if target is None or target_norm in {_norm(value) for value in _ALL}:
        return ("everyone", rows, message)
    if target_norm in {"upstairs", "downstairs"}:
        floor_words = ("up", "first", "second", "top") if target_norm == "upstairs" else ("down", "ground", "bottom")
        chosen = [row for row in rows if any(word in row["floor"].casefold() for word in floor_words)]
        return (target_norm, chosen, message) if chosen else f"I don't know which rooms are {target_norm}. Set floors in Home Assistant."
    chosen = [row for row in rows if _norm(row["area"]) == target_norm]
    if not chosen:
        return f"There's no satellite in the {target}."
    return (f"the {target}", chosen, message)


def _unable_to_announce(connection, targets):
    """FUT-32: satellites the registry says can't take announcements. Unknown counts as able."""
    from declan.ha import satellites
    try:
        registry = satellites.from_connection(connection)
    except (OSError, ValueError, TypeError):
        return []
    return [row for row in targets if satellites.can(registry, row["entity_id"], "announce") is False]


def result(request, connection, *, origin=None, quiet=None):
    if connection is None:
        return ExecutionResult("The Home Assistant connection isn't configured.", Outcome.NOT_CONFIGURED)
    from declan.turn import personality_policy
    try:
        rows = satellites(connection)
        resolved = resolve(request, rows)
        if resolved is None:
            return None
        if isinstance(resolved, str):
            return ExecutionResult(resolved, Outcome.UNRESOLVED)
        label, chosen, message = resolved
        here = next((row for row in rows if origin in {row["entity_id"], row["device"]}), None) if origin else None
        targets = [row for row in chosen if row is not here]
        if not targets:
            return ExecutionResult("There's nobody else to tell. Talk louder, boet.", Outcome.UNRESOLVED)
        if (quiet if quiet is not None else personality_policy.quiet_hours()):
            return ExecutionResult("It's quiet hours. I'm not shouting through the house at this time of night.",
                                   Outcome.UNRESOLVED)
        source = f"Message from the {here['area'].casefold()}: " if here and here["area"] else "Message: "
        spoken = source + message.rstrip(".!?") + "."
        failed = []
        unable = _unable_to_announce(connection, targets)
        if unable and len(unable) == len(targets):
            names = ", ".join(row["area"] or row["entity_id"] for row in unable)
            return ExecutionResult(f"{names} can't take announcements.", Outcome.UNRESOLVED)
        targets = [row for row in targets if row not in unable]
        for row in targets:
            if row["state"] in {"unavailable", "unknown"}:
                failed.append(row["area"] or row["entity_id"])
                continue
            try:
                _call(connection, "/api/services/assist_satellite/announce",
                      {"entity_id": row["entity_id"], "message": spoken, "preannounce": True})
            except HTTPError as error:
                error.close()
                failed.append(row["area"] or row["entity_id"])
            except (OSError, ValueError):
                failed.append(row["area"] or row["entity_id"])
        reached = len(targets) - len(failed)
        if not reached:
            return ExecutionResult(f"I couldn't reach {', '.join(failed)}.", Outcome.UNAVAILABLE)
        where = "everyone" if label == "everyone" else label
        tail = f" I couldn't reach {', '.join(failed)}." if failed else ""
        if unable:
            tail += f" {', '.join(row['area'] or row['entity_id'] for row in unable)} can't take announcements."
        return ExecutionResult(f"Told {where}.{tail}", Outcome.PARTIAL if failed or unable else Outcome.CONFIRMED)
    except HTTPError as error:
        error.close()
        return ExecutionResult("Home Assistant wouldn't list the satellites.", Outcome.UNAVAILABLE)
    except (OSError, ValueError, TypeError):
        return ExecutionResult("I couldn't reach Home Assistant to pass that on.", Outcome.UNAVAILABLE)
