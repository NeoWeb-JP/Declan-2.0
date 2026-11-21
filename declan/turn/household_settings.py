"""Household settings, editable in Settings -> Household (FUT-60, #834).

guest_tone: which lines Declan uses while Guest Mode is on or visitors are
present. "home" (the owner's choice, 21 Nov 2026) keeps his full sass with
guests; "polite" uses the separate guest line set, as before 2.14.

This only changes the wording. Guest Mode authority (sensitive confirmations,
private answers) never depends on it.

A value saved in Settings wins, then DECLAN_GUEST_TONE, then "home".
"""
import json
import os
from pathlib import Path

GUEST_TONES = ("home", "polite")
ENVIRONMENT = {"guest_tone": "DECLAN_GUEST_TONE"}
DEFAULTS = {"guest_tone": "home"}
CHOICES = {"guest_tone": GUEST_TONES}
PATH = Path(__file__).resolve().parents[2] / ".data" / "household-settings.json"


def _valid(key, value):
    return isinstance(value, str) and value in CHOICES[key]


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
        environment = os.environ.get(ENVIRONMENT[key], "").strip().lower()
        if _valid(key, saved.get(key)):
            settings[key], sources[key] = saved[key], "saved"
        elif _valid(key, environment):
            settings[key], sources[key] = environment, "environment"
        else:
            settings[key], sources[key] = default, "default"
    return {"settings": settings, "sources": sources}


def save(payload, path=None):
    path = Path(PATH if path is None else path)
    if (not isinstance(payload, dict) or set(payload) != set(DEFAULTS)
            or not all(_valid(key, value) for key, value in payload.items())):
        raise ValueError("Choose home or polite for the guest tone.")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    return listing(path)


def guest_tone(path=None):
    return listing(path)["settings"]["guest_tone"]


def guest_lines(guest):
    """True only when guest wording is wanted: Guest Mode on and tone polite."""
    return bool(guest) and guest_tone() == "polite"
