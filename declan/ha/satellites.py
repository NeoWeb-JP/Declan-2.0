"""Satellite capability registry (FUT-32, #834). A prerequisite for FUT-34 and FUT-36.

What each Assist satellite can do, so features check instead of assuming
every device is the same:

- ``audio``: play music and sound (a media player on the satellite's device,
  or in its room).
- ``announce``: take announcements (the satellite's ANNOUNCE feature).
- ``reply``: start a conversation and listen for the answer (its
  START_CONVERSATION feature), needed for two-way intercom (FUT-34).
- ``screen``: show pictures or a camera (FUT-36). Home Assistant can't tell,
  so it's off until set in Settings -> Household -> Satellites.

Read from Home Assistant where possible; anything can be overridden in
Settings, and an override wins.
"""
import json
import os
import re
from pathlib import Path

PATH = Path(__file__).resolve().parents[2] / ".data" / "satellite-capabilities.json"
CAPABILITIES = ("audio", "announce", "reply", "screen")
LABELS = {"audio": "play audio", "announce": "take announcements", "reply": "listen for a reply",
          "screen": "show pictures"}
ANNOUNCE, START_CONVERSATION = 1, 2  # AssistSatelliteEntityFeature
_SATELLITE = re.compile(r"assist_satellite\.[a-z0-9_]{1,80}")
_TEMPLATE = (
    "{% set ns = namespace(rows=[]) %}"
    "{% for entity in states.assist_satellite %}"
    "{% set device = device_id(entity.entity_id) %}"
    "{% set area = area_id(entity.entity_id) %}"
    "{% set own = (device_entities(device) if device else []) | select('match', '^media_player[.]') | list %}"
    "{% set room = (area_entities(area) if area else []) | select('match', '^media_player[.]') | list %}"
    "{% set ns.rows = ns.rows + [[entity.entity_id, area_name(entity.entity_id) or '', entity.name or '', "
    "entity.state, entity.attributes.supported_features | default(0) | int, (own + room) | length]] %}"
    "{% endfor %}{{ ns.rows | to_json }}"
)


def _overrides(path=None):
    try:
        data = json.loads(Path(PATH if path is None else path).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {entity: {key: value for key, value in caps.items() if key in CAPABILITIES and type(value) is bool}
            for entity, caps in data.items() if _SATELLITE.fullmatch(entity) and isinstance(caps, dict)}


def read(fetch, *, path=None):
    """[{entity_id, area, name, state, detected, overrides, capabilities}] from HA, with overrides applied.

    ``fetch(template)`` renders a template in Home Assistant.
    """
    rows = fetch(_TEMPLATE)
    if not isinstance(rows, list):
        raise ValueError("Home Assistant didn't list the satellites.")
    overrides = _overrides(path)
    satellites = []
    for row in rows:
        if not (isinstance(row, list) and len(row) == 6 and all(isinstance(value, str) for value in row[:4])
                and type(row[4]) is int and type(row[5]) is int and _SATELLITE.fullmatch(row[0])):
            continue
        entity, area, name, state, features, players = row
        detected = {"audio": players > 0, "announce": bool(features & ANNOUNCE),
                    "reply": bool(features & START_CONVERSATION), "screen": False}
        override = overrides.get(entity, {})
        satellites.append({"entity_id": entity, "area": area, "name": name, "state": state, "detected": detected,
                           "overrides": override, "capabilities": {**detected, **override}})
    return sorted(satellites, key=lambda row: (row["area"] or row["name"] or row["entity_id"]).casefold())


def can(satellites, entity_id, capability):
    """True/False for a known satellite, None when it isn't in the registry (callers then don't block)."""
    for row in satellites or ():
        if row["entity_id"] == entity_id:
            return row["capabilities"][capability]
    return None


def save(entity_id, overrides, *, path=None):
    """Set (True/False) or clear (None) overrides for one satellite."""
    if not isinstance(entity_id, str) or not _SATELLITE.fullmatch(entity_id):
        raise ValueError("That isn't an Assist satellite.")
    if (not isinstance(overrides, dict) or not set(overrides) <= set(CAPABILITIES)
            or not all(value is None or type(value) is bool for value in overrides.values())):
        raise ValueError("Capabilities are audio, announce, reply and screen: on, off or automatic.")
    path = Path(PATH if path is None else path)
    data = _overrides(path)
    current = {**data.get(entity_id, {}), **overrides}
    current = {key: value for key, value in current.items() if value is not None}
    if current:
        data[entity_id] = current
    else:
        data.pop(entity_id, None)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(data, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return data.get(entity_id, {})


def listing(fetch, *, path=None):
    """For Settings: every satellite with what HA detected, the overrides and the result."""
    return read(fetch, path=path)


def from_connection(connection):
    """The registry through Declan's usual HA connection tuple."""
    from declan.ha import ha_reads
    return read(lambda template: ha_reads.template(connection, template, timeout=4))


def describe(row):
    """'The kitchen can play audio, take announcements and listen for a reply, but can't show pictures.'"""
    place = f"The {row['area'].casefold()}" if row["area"] else row["name"] or row["entity_id"]
    yes = [LABELS[key] for key in CAPABILITIES if row["capabilities"][key]]
    no = [LABELS[key] for key in CAPABILITIES if not row["capabilities"][key]]

    def join(items):
        return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]
    if not yes:
        return f"{place} can't do anything useful, as far as Home Assistant says."
    return f"{place} can {join(yes)}" + (f", but can't {join(no)}." if no else ".")


_ASK = re.compile(r"what can (?:the |all the |my )?(?:satellites|speakers|screens|panels) do"
                  r"|what can (?:this|the) (?P<here>satellite|speaker|screen|panel) do"
                  r"|what can (?:the )?(?P<room>[a-z][a-z ]{1,30}?) (?:satellite|speaker|screen|panel) do")


def match(phrase):
    """("satellites", None) for all, ("satellites", "here") or ("satellites", room) | None."""
    if not isinstance(phrase, str):
        return None
    text = " ".join(phrase.casefold().replace("’", "'").split()).strip(" ?.!")
    text = re.sub(r"^(?:declan,? |hey declan,? |howzit declan,? )", "", text)
    found = _ASK.fullmatch(text)
    if not found:
        return None
    return ("satellites", "here" if found["here"] else found["room"])


def result(request, connection, *, origin=None):
    from declan.core.execution_results import ExecutionResult, Outcome
    if request is None:
        return None
    if connection is None:
        return ExecutionResult("The Home Assistant connection isn't configured.", Outcome.NOT_CONFIGURED)
    try:
        rows = from_connection(connection)
    except (OSError, ValueError, TypeError):
        return ExecutionResult("I couldn't ask Home Assistant about the satellites.", Outcome.UNAVAILABLE)
    if not rows:
        return ExecutionResult("I can't see any Assist satellites in Home Assistant.", Outcome.NOT_CONFIGURED)
    which = request[1]
    if which == "here":
        rows = [row for row in rows if origin and origin == row["entity_id"]]
        if not rows:
            return ExecutionResult("I can't tell which satellite this is.", Outcome.UNRESOLVED)
    elif which:
        wanted = " ".join(which.removeprefix("the ").split())
        rows = [row for row in rows if row["area"].casefold() == wanted]
        if not rows:
            return ExecutionResult(f"There's no satellite in the {wanted}.", Outcome.UNRESOLVED)
    return ExecutionResult(" ".join(describe(row) for row in rows), Outcome.CHAT_ANSWER)
