"""Household settings, editable in Settings -> Household (FUT-60, FUT-61, #834).

guest_tone: which lines Declan uses while Guest Mode is on or visitors are
present. "home" (the owner's choice, 21 Nov 2026) keeps his full sass with
guests; "polite" uses the separate guest line set, as before 2.14. This only
changes the wording. Guest Mode authority (sensitive confirmations, private
answers) never depends on it.

shelve_days: once a sass line, roast or response has been said, it rests for
this many days before Declan uses it again (0 turns resting off).

fresh_lines: when a category runs low on rested lines, Declan writes new ones
in the background with the AI, within a small monthly budget.

A value saved in Settings wins, then the environment variable, then the default.
"""
import json
import os
from pathlib import Path

GUEST_TONES = ("home", "polite")
ENVIRONMENT = {"guest_tone": "DECLAN_GUEST_TONE", "shelve_days": "DECLAN_SHELVE_DAYS",
               "fresh_lines": "DECLAN_FRESH_LINES"}
DEFAULTS: dict[str, object] = {"guest_tone": "home", "shelve_days": 3, "fresh_lines": True}
MAX_SHELVE_DAYS = 30
PATH = Path(__file__).resolve().parents[2] / ".data" / "household-settings.json"
_ON = frozenset({"1", "true", "yes", "on"})
_OFF = frozenset({"0", "false", "no", "off"})


def _valid(key, value):
    if key == "guest_tone":
        return isinstance(value, str) and value in GUEST_TONES
    if key == "shelve_days":
        return type(value) is int and 0 <= value <= MAX_SHELVE_DAYS
    if key == "fresh_lines":
        return type(value) is bool
    return False


def _from_environment(key):
    raw = os.environ.get(ENVIRONMENT[key], "").strip().lower()
    if key == "guest_tone":
        return raw if _valid(key, raw) else None
    if key == "shelve_days":
        try:
            value = int(raw)
        except ValueError:
            return None
        return value if _valid(key, value) else None
    return True if raw in _ON else False if raw in _OFF else None


def _saved(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def listing(path=None):
    saved = _saved(PATH if path is None else path)
    settings, sources = {}, {}
    for key, default in DEFAULTS.items():
        environment = _from_environment(key)
        if _valid(key, saved.get(key)):
            settings[key], sources[key] = saved[key], "saved"
        elif environment is not None:
            settings[key], sources[key] = environment, "environment"
        else:
            settings[key], sources[key] = default, "default"
    return {"settings": settings, "sources": sources}


def save(payload, path=None):
    """Save the settings sent. Older panels send only guest_tone; the rest are kept."""
    path = Path(PATH if path is None else path)
    if (not isinstance(payload, dict) or "guest_tone" not in payload or not set(payload) <= set(DEFAULTS)
            or not all(_valid(key, value) for key, value in payload.items())):
        raise ValueError("Choose a guest tone (home or polite), shelve days from 0 to 30, "
                         "and fresh lines on or off.")
    kept = {key: value for key, value in _saved(path).items() if key in DEFAULTS and _valid(key, value)}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps({**kept, **payload}, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return listing(path)


def guest_tone(path=None):
    return listing(path)["settings"]["guest_tone"]


def shelve_days(path=None):
    return listing(path)["settings"]["shelve_days"]


def fresh_lines(path=None):
    return listing(path)["settings"]["fresh_lines"]


def guest_lines(guest):
    """True only when guest wording is wanted: Guest Mode on and tone polite."""
    return bool(guest) and guest_tone() == "polite"
