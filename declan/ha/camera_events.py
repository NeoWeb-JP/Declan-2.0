"""Camera event questions from Frigate (FUT-41, #834).

"Was someone at the front door?", "is anyone in the garden?", "is a pet in
the garden?", "when did a car last arrive?", "is there a car on the drive?".

- Read-only, from the Frigate integration's own Home Assistant entities: the
  ``binary_sensor.<camera or zone>_<object>_occupancy`` sensors (is it there
  now?) and the ``image.<camera or zone>_<object>`` snapshots, whose state is
  the time of the last detection. No AI and no extra cost.
- Unknown people stay "someone": no faces, no names, no identity claims.
- Answers say which camera and roughly when. "Camera offline" and "nothing
  detected" are told apart (FUT-24).
- Hidden in Guest mode (or when Guest mode can't be read).
"""
import re
from datetime import datetime, timedelta

from declan.core.execution_results import ExecutionResult, Outcome
from declan.ha import ha_reads

_OBJECTS = {
    "person": ("someone", "anyone", "anybody", "somebody", "a person", "people", "visitors", "a visitor", "the postman",
               "a delivery", "a courier"),
    "car": ("a car", "cars", "the car", "a vehicle", "a van"),
    "dog": ("a dog", "the dog", "dogs"),
    "cat": ("a cat", "the cat", "cats"),
    "pet": ("a pet", "the pets", "pets", "an animal", "animals", "the animals"),
}
_WORD = {phrase: kind for kind, phrases in _OBJECTS.items() for phrase in phrases}
_WHO = "|".join(sorted((re.escape(phrase) for phrase in _WORD), key=len, reverse=True))
_PREP = r"(?P<prep>at|in|on|by|outside|near) (?:the |my |our )?(?P<place>[a-z][a-z ]{1,30}?)"
_PATTERNS = (
    ("now", re.compile(rf"(?:is|are) (?:there )?(?P<who>{_WHO}) {_PREP}(?: (?:now|right now|at the moment))?")),
    ("was", re.compile(rf"(?:was|were|has|have) (?:there )?(?P<who>{_WHO})(?: been| come| called)? {_PREP}"
                       rf"(?: (?:today|earlier|this morning|this afternoon|tonight|recently))?")),
    ("was", re.compile(rf"did (?P<who>{_WHO}) (?:come|call|stop by|turn up) {_PREP}(?: (?:today|earlier))?")),
    ("when", re.compile(rf"when (?:did|was) (?P<who>{_WHO}) last (?:arrive|seen|come|there|here|detected)"
                        rf"(?: {_PREP})?")),
    ("when", re.compile(rf"when was (?:the )?last (?P<last>person|car|dog|cat|pet|visitor)(?: {_PREP})?"
                        r"(?: seen| spotted| detected)?")),
)
_TEMPLATE = (
    "{% set ns = namespace(rows=[]) %}"
    "{% for entity in integration_entities('frigate') %}"
    "{% if entity.startswith('binary_sensor.') and entity.endswith('_occupancy') %}"
    "{% set image = 'image.' ~ entity[14:-10] %}"
    "{% set ns.rows = ns.rows + [[entity, states(entity), "
    "(states[entity].last_changed.isoformat() if states[entity] else ''), states(image)]] %}"
    "{% elif entity.startswith('camera.') %}"
    "{% set ns.rows = ns.rows + [[entity, states(entity), '', '']] %}"
    "{% endif %}{% endfor %}{{ ns.rows | to_json }}"
)
_OCCUPANCY = re.compile(r"binary_sensor\.(?P<place>[a-z0-9_]+?)_(?P<object>person|car|dog|cat|bird|bicycle|motorcycle"
                        r"|package|horse|bear|deer|fox)_occupancy")
_OFFLINE = frozenset({"unavailable", "unknown", ""})
_NOUNS = {"person": "someone", "car": "a car", "dog": "a dog", "cat": "a cat"}

GUEST_LINES = (
    "The cameras are household business, my bru.",
    "Nice try. Ask your host what the cameras saw.",
    "I'm not telling visitors what the cameras see. Security, boet.",
)
GUEST_TOPIC = "refusing to tell a guest what the security cameras have seen"


def match(phrase):
    """(kind, object, prep or None, place or None) | None. kind: now, was, when."""
    if not isinstance(phrase, str):
        return None
    text = " ".join(phrase.casefold().replace("’", "'").split()).strip(" ?.!")
    text = re.sub(r"^(?:declan,? |hey declan,? |howzit declan,? )", "", text)
    text = re.sub(r",? declan$", "", text)
    for kind, pattern in _PATTERNS:
        found = pattern.fullmatch(text)
        if not found:
            continue
        groups = found.groupdict()
        who = groups.get("who")
        obj = _WORD.get(who) if who else {"visitor": "person"}.get(groups.get("last") or "", groups.get("last"))
        place = (groups.get("place") or "").strip() or None
        if place in {"home", "the house", "house", "in"}:
            return None  # "is anyone at home?" is FUT-30
        return (kind, obj, groups.get("prep"), place) if obj else None
    return None


def read(connection):
    rows = ha_reads.template(connection, _TEMPLATE)
    if not isinstance(rows, list):
        raise ValueError("Home Assistant didn't list the Frigate cameras.")
    cameras, sensors = {}, []
    for row in rows:
        if not (isinstance(row, list) and len(row) == 4 and all(isinstance(value, str) for value in row)):
            continue
        entity, state, changed, last = row
        if entity.startswith("camera."):
            cameras[entity.split(".", 1)[1]] = state
        elif found := _OCCUPANCY.fullmatch(entity):
            sensors.append({"place": found["place"], "object": found["object"], "state": state,
                            "changed": _time(changed), "last": _time(last)})
    return cameras, sensors


def _time(value):
    try:
        moment = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return moment.astimezone() if moment.tzinfo else moment.astimezone()


def _words(place):
    return set(place.replace("_", " ").split()) - {"the", "camera", "cam"}


def places(sensors):
    return sorted({sensor["place"] for sensor in sensors})


def resolve(spoken, sensors):
    """The Frigate camera or zone for a spoken place ("door" -> front_door), or None."""
    wanted = _words(spoken.replace("drive", "driveway") if spoken.endswith("drive") else spoken)
    names = places(sensors)
    exact = [name for name in names if _words(name) == wanted]
    if exact:
        return exact[0]
    partial = [name for name in names if wanted <= _words(name) or _words(name) <= wanted]
    return min(partial, key=len) if partial else None


def when(moment, now=None):
    now = now or datetime.now().astimezone()
    seconds = (now - moment).total_seconds()
    if seconds < 120:
        return "just now"
    if seconds < 3600:
        return f"about {round(seconds / 60)} minutes ago"
    if moment.date() == now.date():
        return f"at {moment:%H:%M}"
    if moment.date() == (now - timedelta(days=1)).date():
        return f"yesterday at {moment:%H:%M}"
    if seconds < 7 * 86400:
        return f"on {moment:%A} at {moment:%H:%M}"
    return f"on {moment.day} {moment:%B}"


def _last(sensor):
    """When this object was last seen there: now, or its last snapshot / the moment it left."""
    if sensor["state"] == "on":
        return "now"
    return sensor["last"] or sensor["changed"]


def _guest_line():
    from declan.turn import line_freshness
    return line_freshness.pick("cameras:guest", GUEST_LINES, topic=GUEST_TOPIC)


def _where(prep, place):
    name = place.replace("_", " ")
    if not prep:
        words = set(name.split())
        prep = ("on" if words & {"drive", "driveway", "road", "street", "patio", "deck", "porch"}
                else "in" if words & {"garden", "yard", "garage", "back", "shed"} else "at")
    return f" {prep} the {name}"


def answer(request, cameras, sensors, *, now=None):
    kind, obj, prep, spoken = request
    now = now or datetime.now().astimezone()
    objects = {"dog", "cat"} if obj == "pet" else {obj}
    if spoken:
        place = resolve(spoken, sensors)
        if place is None:
            return ExecutionResult(f"I haven't got a camera on the {spoken}.", Outcome.UNRESOLVED)
        chosen = [sensor for sensor in sensors if sensor["place"] == place and sensor["object"] in objects]
        if not chosen:
            return ExecutionResult(f"The {place.replace('_', ' ')} camera doesn't look for {_label(obj)}.",
                                   Outcome.UNRESOLVED)
        camera_state = cameras.get(place)
        offline = camera_state in _OFFLINE if camera_state is not None else all(
            sensor["state"] in _OFFLINE for sensor in chosen)
        if offline:
            return ExecutionResult(f"The {place.replace('_', ' ')} camera is offline, so I can't tell.",
                                   Outcome.UNAVAILABLE)
    else:
        chosen = [sensor for sensor in sensors if sensor["object"] in objects]
        if not chosen:
            return ExecutionResult(f"None of the cameras look for {_label(obj)}.", Outcome.UNRESOLVED)
        place = None
    present = [sensor for sensor in chosen if sensor["state"] == "on"]
    seen = sorted(((moment, sensor) for sensor in chosen if (moment := _last(sensor)) not in (None, "now")),
                  key=lambda pair: pair[0], reverse=True)
    if kind == "now":
        where = _where(prep, place)
        if present:
            return ExecutionResult(f"Yes, there's {_noun(present[0]['object'])}{where} right now.", Outcome.CHAT_ANSWER)
        tail = f" Last seen {when(seen[0][0], now)}." if seen and seen[0][0].date() == now.date() else ""
        return ExecutionResult(f"No, nothing{where} right now.{tail}" if obj != "person"
                               else f"No, nobody{where} right now.{tail}", Outcome.CHAT_ANSWER)
    if present:
        sensor = present[0]
        return ExecutionResult(f"There's {_noun(sensor['object'])}{_where(prep, sensor['place'])} right now.",
                               Outcome.CHAT_ANSWER)
    if not seen:
        where = _where(prep, place) if place else ""
        return ExecutionResult(f"Frigate hasn't seen {_label(obj)}{where} lately.", Outcome.CHAT_ANSWER)
    moment, sensor = seen[0]
    where = _where(prep if place else None, sensor["place"])
    noun = _noun(sensor["object"]).capitalize()
    if kind == "was" and moment.date() != now.date():
        return ExecutionResult(f"Not today. {noun} was last{where} {when(moment, now)}.", Outcome.CHAT_ANSWER)
    lead = "Yes, " + _noun(sensor["object"]) if kind == "was" else noun
    return ExecutionResult(f"{lead} was{where} {when(moment, now)}.", Outcome.CHAT_ANSWER)


def _noun(obj):
    return _NOUNS.get(obj, f"a {obj}")


def _label(obj):
    return {"person": "people", "pet": "pets"}.get(obj, f"{obj}s")


def result(request, connection, *, guest, now=None):
    if request is None:
        return None
    if guest:
        return ExecutionResult(_guest_line(), Outcome.REJECTED)
    if connection is None:
        return ExecutionResult("The Home Assistant connection isn't configured.", Outcome.NOT_CONFIGURED)
    try:
        cameras, sensors = read(connection)
    except (OSError, ValueError, TypeError):
        return ExecutionResult("I couldn't ask Home Assistant about the cameras.", Outcome.UNAVAILABLE)
    if not sensors:
        return ExecutionResult("I can't see Frigate's cameras in Home Assistant.", Outcome.NOT_CONFIGURED)
    return answer(request, cameras, sensors, now=now)
