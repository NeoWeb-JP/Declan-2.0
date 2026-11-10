"""Safe alternate-reply lookup for an unavailable preferred TTS voice.

Never substitute speech outside a pre-approved, semantically interchangeable
personality pool. Dynamic factual replies, warnings, and unrecognised text
MUST be spoken exactly as requested (by XTTS if necessary).
"""
from __future__ import annotations

import json
from pathlib import Path

SAFE_ACTIONS = frozenset({"general", "on", "off", "brightness", "morning"})
HOME_MODES = ("Home",)
GUEST_MODES = ("Guest",)


def category_alternatives(message: str, catalogue: dict, *, guest: bool) -> tuple[str, ...]:
    """Only return other exact catalogue lines from the SAME action and privacy mode.

    Source message must already be an exact member of that approved pool.
    If a sentence contains a dynamic fact or custom text, return no alternatives.
    """
    modes = GUEST_MODES if guest else HOME_MODES
    for action in SAFE_ACTIONS:
        pool = []
        for mode in modes:
            entries = catalogue.get(mode, {}).get(action, [])
            if not isinstance(entries, list):
                continue
            pool.extend(x for x in entries if isinstance(x, str) and x.strip())
        if message in pool:
            return tuple(dict.fromkeys(x for x in pool if x != message))
    return ()


def load_catalogue(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ValueError("Invalid Declan response catalogue")
    return value
