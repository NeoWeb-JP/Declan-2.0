"""Editable everyday reply categories. No command dispatch or household targets."""
import sqlite3
from dataclasses import dataclass

from declan.core import history
from declan.turn import response_library as library


@dataclass(frozen=True)
class ResponseCategory:
    key: str
    name: str


CATEGORIES = (
    ResponseCategory("lights_on", "Lights: turn on"),
    ResponseCategory("lights_off", "Lights: turn off"),
    ResponseCategory("brightness", "Lights: brightness"),
    ResponseCategory("full_brightness", "Lights: full brightness"),
    ResponseCategory("already_set", "Lights: already set"),
    ResponseCategory("mixed_lighting", "Lights: mixed changes"),
    ResponseCategory("lights_status", "Lights: status"),
    ResponseCategory("device_status", "Device status"),
    ResponseCategory("timer_set", "Timers: set"),
    ResponseCategory("timer_adjusted", "Timers: adjust"),
    ResponseCategory("timer_cancelled", "Timers: cancel"),
    ResponseCategory("timer_stopped", "Timers: stop alarm"),
    ResponseCategory("weather", "Weather"),
    ResponseCategory("time", "Time"),
    ResponseCategory("greeting", "Greetings"),
    ResponseCategory("memory", "Conversation memory"),
)
KEYS = frozenset(category.key for category in CATEGORIES)


def catalog():
    return [{"entity_id": "command:" + row.key, "name": row.name, "kind": "command"}
            for row in CATEGORIES]


def item(entity):
    if not isinstance(entity, str) or not entity.startswith("command:") or entity[8:] not in KEYS:
        raise ValueError("Select a supported command response")
    return {"entity_id": entity}


def defaults(row):
    from declan.turn import personality
    key = item(row.get("entity_id"))["entity_id"][8:]
    profile: dict[str, dict[str, dict[str, list[str]]]] = {phase: {mode: {action: [] for action in library.ACTIONS}
                      for mode in library.MODES} for phase in library.PHASES}
    for mode, guest in (("sass", False), ("guest", True)):
        profile["completed"][mode]["default"] = list(personality.LINES[key][guest])
    return profile


def snapshot(row):
    return library.snapshot(row, defaults)


def save(row, profile, expected):
    profile = library.validate(profile)
    # Everyday categories have no background acknowledgement or directional slots.
    if any(lines for phase, modes in profile.items() for actions in modes.values()
           for action, lines in actions.items() if phase == "requested" or action != "default"):
        raise ValueError("Use the default completed or failure list for command responses")
    return library.save(row, profile, expected, defaults)


def selected(category, guest, phase="completed"):
    """None means unchanged built-in behaviour; empty means explicitly no banter."""
    if category not in KEYS:
        return None
    row = item("command:" + category)
    try:
        with history.database() as db:
            library._table(db)
            saved = db.execute("SELECT 1 FROM routine_responses WHERE entity=?",
                               (row["entity_id"],)).fetchone()
        if saved is None:
            return None
        return library.select(row, phase, guest, defaults=defaults)
    except (OSError, ValueError, sqlite3.Error):
        return None


def failure(category, original, *, guest):
    line = selected(category, guest, "failure")
    return (line + " " if line else "") + original
