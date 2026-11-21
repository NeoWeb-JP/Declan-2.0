"""Shared response validation, persistence and selection, independent of routing."""
import hashlib
import json

from declan.core import history

PHASES = ("requested", "completed", "failure")
MODES = ("sass", "guest")
ACTIONS = ("default", "start", "end", "toggle")


def validate(profile):
    if not isinstance(profile, dict) or set(profile) != set(PHASES):
        raise ValueError("Invalid response sections")
    clean: dict[str, dict[str, dict[str, list[str]]]] = {}
    for phase in PHASES:
        section = profile[phase]
        if not isinstance(section, dict) or set(section) != set(MODES):
            raise ValueError("Supply sass and guest lists")
        clean[phase] = {}
        for mode in MODES:
            actions = section[mode]
            if not isinstance(actions, dict) or set(actions) != set(ACTIONS):
                raise ValueError("Invalid response actions")
            clean[phase][mode] = {}
            for action in ACTIONS:
                lines = actions[action]
                if not isinstance(lines, list) or len(lines) > 100:
                    raise ValueError("Use at most 100 responses per list")
                if any(not isinstance(line, str) or not 1 <= len(line.strip()) <= 1000
                       or any(ord(c) < 32 and c not in '\n\t' for c in line) for line in lines):
                    raise ValueError("Responses must contain 1 to 1000 characters")
                cleaned = [line.strip() for line in lines]
                if len(set(cleaned)) != len(cleaned):
                    raise ValueError("Remove duplicate responses in each list")
                clean[phase][mode][action] = cleaned
    if len(json.dumps(clean).encode()) > 120000:
        raise ValueError("Response collection is too large")
    return clean


def _table(db):
    db.execute("CREATE TABLE IF NOT EXISTS routine_responses (entity TEXT PRIMARY KEY, payload TEXT NOT NULL)")


def revision(profile):
    return hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest()


def snapshot(item, defaults):
    with history.database() as db:
        _table(db)
        row = db.execute("SELECT payload FROM routine_responses WHERE entity=?", (item['entity_id'],)).fetchone()
    profile = validate(json.loads(row[0])) if row else defaults(item)
    return {"profile": profile, "expected": revision(profile)}


def save(item, profile, expected, defaults):
    profile = validate(profile)
    if not isinstance(expected, str) or len(expected) != 64:
        raise ValueError("Reload responses before saving")
    with history.database() as db:
        db.execute("BEGIN IMMEDIATE")
        _table(db)
        row = db.execute("SELECT payload FROM routine_responses WHERE entity=?", (item['entity_id'],)).fetchone()
        current = validate(json.loads(row[0])) if row else defaults(item)
        if revision(current) != expected:
            raise ValueError("Responses changed elsewhere. Reload before saving.")
        db.execute("INSERT OR REPLACE INTO routine_responses VALUES (?, ?)",
                   (item['entity_id'], json.dumps(profile)))
    return {"saved": True, "expected": revision(profile)}


def select(item, phase, guest, action="default", *, defaults):
    """Small lists and empty lists are valid.

    Guest lines are used only when Guest Mode is on and Settings -> Household
    -> Guest tone is "polite"; otherwise guests hear the Home sass (FUT-60).
    """
    from declan.turn.household_settings import guest_lines
    mode = "guest" if guest_lines(guest) else "sass"
    profile = snapshot(item, defaults)["profile"]
    section = profile[phase][mode]
    action = action if action in ACTIONS else "default"
    lines = section[action] or (section["default"] if action != "default" else [])
    if not lines:
        return ""
    # FUT-61: used lines rest for days; a low pool is topped up in Declan's voice.
    from declan.turn import line_freshness
    name = str(item.get("name") or item["entity_id"])
    if phase == "failure":
        topic = f"after the {name} request could not be completed (never suggest it worked)"
    else:
        topic = f"after {name} ({action})" if action != "default" else f"after {name}"
    key = ":".join(("library", item["entity_id"], phase, mode, action))
    return line_freshness.pick(key, lines, topic=topic, polite=mode == "guest")


