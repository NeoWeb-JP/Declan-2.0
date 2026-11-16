"""Persistent per-script response lists. Text never changes execution outcomes."""
import hashlib
import json
import re
import sqlite3
from random import SystemRandom
from threading import Lock

import history

ENTITY = re.compile(r"script\.[a-z0-9_]{1,200}\Z")
PHASES = ("requested", "completed", "failure")
MODES = ("sass", "guest")
ACTIONS = ("default", "start", "end", "toggle")
_random = SystemRandom()
_lock = Lock()
_recent = {}


def validate(profile):
    if not isinstance(profile, dict) or set(profile) != set(PHASES):
        raise ValueError("Invalid response sections")
    clean = {}
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


def defaults(item):
    import personality_policy as policy
    import personality
    import script_discovery
    profile = {phase: {mode: {action: [] for action in ACTIONS} for mode in MODES} for phase in PHASES}
    aliases = script_discovery.phrases(item)
    category = next((name for name, aliases_for in (
        ("morning", {"good morning"}), ("night", {"good night"}),
        ("sexy", {"sexy time"}), ("movie", {"movie time", "start movie time", "end movie time"}),
        ("dinner", {"dinner", "dinner is served", "dinner time"}),
    ) if aliases & aliases_for), "general")
    for mode, guest in (("sass", False), ("guest", True)):
        generic = policy._GUEST if guest else policy._SAVAGE
        profile["completed"][mode]["default"] = list(generic)
        profile["requested"][mode]["default"] = ["I'll start the routine."]
        if category in {"morning", "night"}:
            prefix = "Good morning. " if category == "morning" else "Good night. "
            lines = getattr(policy, f"_{category.upper()}_{'GUEST' if guest else 'HOME'}")
            profile["requested"][mode]["default"] = [prefix + line for line in lines]
            profile["completed"][mode]["default"] = list(personality.LINES[f"good_{category}"][guest])
        elif category in {"movie", "sexy"}:
            table = getattr(policy, f"_{category.upper()}_{'GUEST' if guest else 'HOME'}")
            profile["requested"][mode]["default"] = []
            for action, lines in table.items():
                profile["requested"][mode][action] = list(lines)
                legacy = f"movie_{action}" if category == "movie" else f"sexy_time_{action}"
                profile["completed"][mode][action] = list(personality.LINES.get(legacy, (generic, generic))[guest])
        elif category == "dinner":
            lines = policy._DINNER_GUEST if guest else policy._DINNER_HOME
            profile["completed"][mode]["default"] = list(lines)
    return profile


def _table(db):
    db.execute("CREATE TABLE IF NOT EXISTS routine_responses (entity TEXT PRIMARY KEY, payload TEXT NOT NULL)")


def revision(profile):
    return hashlib.sha256(json.dumps(profile, sort_keys=True).encode()).hexdigest()


def snapshot(item):
    with history.database() as db:
        _table(db)
        row = db.execute("SELECT payload FROM routine_responses WHERE entity=?", (item['entity_id'],)).fetchone()
    profile = validate(json.loads(row[0])) if row else defaults(item)
    return {"profile": profile, "expected": revision(profile)}


def save(item, profile, expected):
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


def select(item, phase, guest, action="default"):
    """Small lists and empty lists are valid; never leak sass into Guest Mode."""
    mode = "guest" if guest else "sass"
    profile = snapshot(item)["profile"]
    section = profile[phase][mode]
    action = action if action in ACTIONS else "default"
    lines = section[action] or (section["default"] if action != "default" else [])
    if not lines:
        return ""
    key = (str(history.DATABASE), item['entity_id'], phase, mode, action)
    with _lock:
        previous = _recent.get(key)
        line = _random.choice([line for line in lines if line != previous] or lines)
        if len(_recent) > 4000:
            _recent.clear()
        _recent[key] = line
    return line


def render(selection, outcome, original, *, guest=False):
    """Replace ordinary routine wording, retain diagnostics and informative scripts."""
    kind, options = selection
    if not kind.startswith("auto:"):
        return original
    phase = ("requested" if outcome == "started" else "completed" if outcome in
             {"confirmed", "reported_success", "execution_completed"} else
             "failure" if outcome in {"failed", "partial", "unverified", "unresolved", "not_configured", "cancelled"} else None)
    if phase is None:
        return original
    entity = kind[5:]
    item = {"entity_id": entity, "name": entity[7:].replace('_', ' ')}
    # Runtime uses the same live name/capabilities as the editor when available.
    import script_discovery
    with script_discovery._CACHE_LOCK:
        for _, rows in script_discovery._CACHE.values():
            found = next((row for row in rows if row['entity_id'] == entity), None)
            if found:
                item = found
                break
    action = options.get("requested_action", options.get("operation", "default"))
    try:
        # Informational scripts retain their returned content until the user
        # explicitly saves response lists for them.
        if options.get("_declan_expect_response"):
            with history.database() as db:
                _table(db)
                saved = db.execute("SELECT 1 FROM routine_responses WHERE entity=?", (entity,)).fetchone()
            if not saved:
                return original
        line = select(item, phase, guest, action)
    except (OSError, ValueError, sqlite3.Error):
        return original
    if phase == "failure":
        return (line + " " if line else "") + original
    return line or ("Routine requested." if phase == "requested" else "Routine finished.")
