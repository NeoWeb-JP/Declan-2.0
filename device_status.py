"""Resolve and describe live Home Assistant device states without changing them."""

import re


DOMAINS = {"binary_sensor", "climate", "cover", "fan", "light", "media_player", "switch"}
QUERY = re.compile(r"(?:is|are) (.+?) (on|off|open|closed|up|down|playing|running)")
STATUS = re.compile(r"(?:what is|what's) (?:the )?status of (.+)")
FOLLOW_UP = re.compile(r"(?:what|how) about (.+)")
PROJECTOR = "media_player.toptro_vg03f3_037f0808_television"
SCREEN = "cover.living_room_projector_screen"


def parse(phrase, previous):
    phrase = phrase.replace("’", "'")
    query = QUERY.fullmatch(phrase)
    if query:
        name, requested = query.groups()
    else:
        query = STATUS.fullmatch(phrase) or (FOLLOW_UP.fullmatch(phrase) if previous else None)
        if not query:
            return None
        name, requested = query[1], None
    name = name.removeprefix("the ")
    if name in {"it", "that", "that device"}:
        return previous, requested
    return name, requested


def describe(name, requested, inventory):
    if not name:
        return "Which device should I check?", "unresolved", None
    candidates = {}
    devices = {}
    for item in inventory:
        entity = item.get("entity_id") if isinstance(item, dict) else None
        if not isinstance(entity, str):
            continue
        domain, _, slug = entity.partition(".")
        if domain not in DOMAINS or not slug:
            continue
        attrs = item.get("attributes")
        attrs = attrs if isinstance(attrs, dict) else {}
        friendly = attrs.get("friendly_name")
        label = friendly.strip() if isinstance(friendly, str) and friendly.strip() else slug.replace("_", " ")
        devices[entity] = (label, item.get("state"), attrs)
        aliases = {entity, slug.replace("_", " "), " ".join(label.casefold().split())}
        if name in aliases:
            candidates[entity] = label

    if not candidates:
        fallback = {"projector": PROJECTOR, "projector screen": SCREEN}.get(name)
        if fallback in devices:
            candidates[fallback] = name.capitalize()
    if not candidates:
        return f"I couldn't find a Home Assistant device called {name}.", "unresolved", None
    if name in candidates:
        candidates = {name: candidates[name]}
    elif requested in {"on", "off"}:
        lights = {entity: label for entity, label in candidates.items() if entity.startswith("light.")}
        if lights:
            candidates = lights
    if len(candidates) > 1:
        labels = sorted(set(candidates.values()), key=str.casefold)
        if len(labels) == 1:
            reply = f"Which device did you mean? More than one is named {labels[0]}. Which room?"
        else:
            reply = f"Which device did you mean? I found {', '.join(labels)}."
        return reply, "unresolved", None
    entity = next(iter(candidates))
    _, state, attrs = devices[entity]
    label = candidates[entity]
    if entity == PROJECTOR:
        label = "Projector"
    if not isinstance(state, str) or state in {"", "unknown", "unavailable"}:
        return f"I couldn't verify {label}'s current state.", "unavailable", entity

    if entity == SCREEN and requested in {"up", "down"} and state in {"open", "closed"}:
        position = attrs.get("current_position")
        if state == "closed" or type(position) in (int, float) and 0 <= position <= 5:
            state = "up"
        elif type(position) in (int, float) and 80 <= position <= 100:
            state = "down"
        elif type(position) in (int, float) and 5 < position < 80:
            state = f"partway down at {position:g} percent"
        else:
            return f"{label} reports it's open. I couldn't verify how far down it is.", "partial", entity
    return f"{label} is {state.replace('_', ' ')}.", "confirmed", entity
