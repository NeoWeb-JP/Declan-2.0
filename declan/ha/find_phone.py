"""Find my phone (FUT-33, #834).

"Ring Edd's phone", "find my phone", "I can't find my phone".

- People and their phones come from Home Assistant: each ``person`` entity's
  device trackers, and the companion app's notify service for that phone
  (``device_tracker.edd_iphone`` -> ``notify.mobile_app_edd_iphone``).
- The notification asks to make a noise even on silent: Android plays it on
  the alarm stream; iPhones only ring on silent if critical alerts are
  allowed for the Home Assistant app (Settings -> Notifications -> Home
  Assistant -> Critical Alerts), so Declan reminds you once for an iPhone.
- "My phone": speaker recognition isn't reliable enough to know whose, so
  with more than one phone in the house Declan asks whose.
- Declan can't know if the phone actually rang; he says he sent it.
"""
import re

from declan.core.execution_results import ExecutionResult, Outcome
from declan.ha import ha_reads

_PHONE = r"(?:phone|mobile|cell ?phone|iphone|cell)"
_WHO = r"(?P<who>my|(?P<name>[a-z][a-z' -]{0,30}?)'s)"
_PATTERNS = (
    re.compile(rf"(?:ring|call|buzz|ping|find|locate|beep) {_WHO} {_PHONE}(?: for me)?(?: please)?"),
    re.compile(rf"(?:help me find|can you (?:ring|find|call)|could you (?:ring|find|call)) {_WHO} {_PHONE}(?: for me)?(?: please)?"),
    re.compile(rf"i (?:can't|cannot|can not) find {_WHO} {_PHONE}"),
    re.compile(rf"i(?:'ve| have)? lost {_WHO} {_PHONE}"),
    re.compile(rf"(?P<lost>[a-z][a-z' -]{{0,30}}?) (?:can't|cannot) find (?:his|her|their) {_PHONE}"),
)
_TEMPLATE = (
    "{% set ns = namespace(people=[]) %}"
    "{% for person in states.person %}"
    "{% set phones = namespace(rows=[]) %}"
    "{% for tracker in state_attr(person.entity_id, 'device_trackers') or [] %}"
    "{% set device = device_id(tracker) %}"
    "{% set phones.rows = phones.rows + [[tracker, ((device_attr(device, 'model') or '') if device else '') | string, "
    "((device_attr(device, 'manufacturer') or '') if device else '') | string]] %}"
    "{% endfor %}"
    "{% set ns.people = ns.people + [[person.entity_id, person.name, phones.rows]] %}"
    "{% endfor %}{{ ns.people | to_json }}"
)
_TRACKER = re.compile(r"device_tracker\.([a-z0-9_]{1,80})")
MESSAGE = "Declan's looking for this phone. Here it is!"


def match(phrase):
    """("ring", spoken name or None for "my") | None."""
    if not isinstance(phrase, str):
        return None
    text = " ".join(phrase.casefold().replace("’", "'").split()).strip(" ?.!")
    text = re.sub(r"^(?:declan,? |hey declan,? |howzit declan,? |please )", "", text)
    text = re.sub(r",? (?:declan|please)$", "", text)
    for pattern in _PATTERNS:
        if found := pattern.fullmatch(text):
            groups = found.groupdict()
            if groups.get("lost"):
                return ("ring", groups["lost"].strip())
            return ("ring", None if groups.get("who") == "my" else (groups.get("name") or "").strip() or None)
    return None


def phones(connection):
    """[{person, name, phones: [{service, iphone}]}] for people with a companion-app phone."""
    rows = ha_reads.template(connection, _TEMPLATE)
    if not isinstance(rows, list):
        raise ValueError("Home Assistant didn't list people.")
    people = []
    for row in rows:
        if not (isinstance(row, list) and len(row) == 3 and isinstance(row[0], str) and isinstance(row[1], str)
                and isinstance(row[2], list)):
            continue
        found = []
        for tracker in row[2]:
            if not (isinstance(tracker, list) and len(tracker) == 3 and all(isinstance(value, str) for value in tracker)):
                continue
            entity = _TRACKER.fullmatch(tracker[0])
            if entity:
                found.append({"service": "mobile_app_" + entity.group(1),
                              "iphone": "iphone" in tracker[1].casefold() or tracker[2].casefold() == "apple"})
        people.append({"person": row[0], "name": row[1], "phones": found})
    return people


def _norm(text):
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", text.casefold()).split())


def _find(name, people):
    wanted = _norm(name)
    for row in people:
        full = _norm(row["name"])
        object_id = _norm(row["person"].split(".", 1)[-1].replace("_", " "))
        if wanted in {full, object_id} or (full and wanted == full.split()[0]):
            return row
    return None


def _payload():
    return {"title": "Declan", "message": MESSAGE,
            "data": {"tag": "declan-find-phone", "ttl": 0, "priority": "high", "channel": "alarm_stream",
                     "push": {"sound": {"name": "default", "critical": 1, "volume": 1.0},
                              "interruption-level": "critical"}}}


def result(request, connection):
    if request is None:
        return None
    if connection is None:
        return ExecutionResult("The Home Assistant connection isn't configured.", Outcome.NOT_CONFIGURED)
    try:
        people = phones(connection)
    except (OSError, ValueError, TypeError):
        return ExecutionResult("I couldn't ask Home Assistant about the phones.", Outcome.UNAVAILABLE)
    with_phones = [row for row in people if row["phones"]]
    name = request[1]
    if name is None:
        if len(with_phones) != 1:
            if not with_phones:
                return ExecutionResult("I can't find any phones with the Home Assistant app in People.",
                                       Outcome.NOT_CONFIGURED)
            return ExecutionResult("Whose phone? Say \"ring Edd's phone\". I can't tell you lot apart by voice yet.",
                                   Outcome.UNRESOLVED)
        person = with_phones[0]
    else:
        person = _find(name, people)
        if person is None:
            return ExecutionResult(f"I don't know a {name.title()} in Home Assistant.", Outcome.UNRESOLVED)
        if not person["phones"]:
            return ExecutionResult(f"{person['name']} hasn't got a phone with the Home Assistant app that I can see.",
                                   Outcome.NOT_CONFIGURED)
    sent, iphone = 0, False
    for phone in person["phones"]:
        try:
            ha_reads.call(connection, f"/api/services/notify/{phone['service']}", _payload())
        except (OSError, ValueError):
            continue
        sent += 1
        iphone = iphone or phone["iphone"]
    owner = person["name"]
    if not sent:
        return ExecutionResult(f"I couldn't reach {owner}'s phone. Check the Home Assistant app is signed in.",
                               Outcome.FAILED)
    reply = f"Ringing {owner}'s phone. Follow the noise."
    if iphone:
        reply += " If it's on silent, an iPhone only rings if critical alerts are allowed for the Home Assistant app."
    return ExecutionResult(reply, Outcome.REQUESTED)
