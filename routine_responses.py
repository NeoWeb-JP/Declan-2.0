"""Per-script defaults and rendering; shared storage is in response_library."""
import re
import sqlite3

import history
import response_library

ENTITY = re.compile(r"script\.[a-z0-9_]{1,200}\Z")
PHASES = response_library.PHASES
MODES = response_library.MODES
ACTIONS = response_library.ACTIONS
validate = response_library.validate
revision = response_library.revision
_table = response_library._table


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


def snapshot(item):
    return response_library.snapshot(item, defaults)


def save(item, profile, expected):
    return response_library.save(item, profile, expected, defaults)


def select(item, phase, guest, action="default"):
    return response_library.select(item, phase, guest, action, defaults=defaults)


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
