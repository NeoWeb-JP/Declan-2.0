"""Personality sliders for the household and for guests (Settings -> Household).

Seven traits, each 1-10, saved separately for the household and for guests:

- sass:       attitude and sarcasm; low sass falls back to the gentler guest lines
- rudeness:   bluntness and impatience; low rudeness also uses the gentler lines
- humour:     how often a joke is added to a plain reply
- slang:      "Saffa-ness"; 1-3 strips "my bru" and drops lines with SA slang
- chattiness: how much he says; 1 adds no extra line, 2-3 keeps lines short
- swearing:   1-3 clean, 4-5 mild ("bloody"), 6-8 strong, 9-10 anything
- insults:    1-3 none, 4-6 mild ("muppet"), 7-10 personal

Which set applies follows the same rule as the guest persona: Guest Mode on,
or visitors present (or either unknown) means the guest set. The defaults are
Declan as he was before the sliders, for both sets, so nothing changes until
a slider moves.

Generated (learned) lines are stored against a fingerprint of the sliders. A
save that changes the sliders forgets every generated line, resting record
and top-up attempt whose fingerprint is no longer in use, so the new settings
take over straight away. The owner's own edited lines are never touched.

This module only shapes wording. It never changes what Declan does, Guest
Mode authority or sensitive confirmations.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from contextvars import ContextVar
from pathlib import Path
from random import SystemRandom

TRAITS = ("sass", "rudeness", "humour", "slang", "chattiness", "swearing", "insults")
LABELS = {"sass": "Sass", "rudeness": "Rudeness", "humour": "Humour", "slang": "Saffa-ness",
          "chattiness": "Chattiness", "swearing": "Swearing", "insults": "Insults"}
AUDIENCES = ("household", "guests")
MINIMUM, MAXIMUM = 1, 10
# Declan as he was before the sliders (rude, sassy, South African, full sass for guests).
BASE = {"sass": 8, "rudeness": 8, "humour": 7, "slang": 6, "chattiness": 5, "swearing": 9, "insults": 8}
DEFAULTS = {audience: dict(BASE) for audience in AUDIENCES}
PATH = Path(__file__).resolve().parents[2] / ".data" / "personality.json"

LOGGER = logging.getLogger(__name__)
_RANDOM = SystemRandom()
_UNSET = object()
_GUEST_MODE: ContextVar = ContextVar("declan_guest_mode", default=_UNSET)
_VISITORS: ContextVar = ContextVar("declan_visitors_present", default=_UNSET)

# Swearing: the level a line needs before it may be said.
_SWEAR = (
    (9, re.compile(r"\bf+u+c+k\w*|\bmotherf\w*", re.I)),
    (6, re.compile(r"\b(?:bastards?|bullshit|bitch\w*|shit\w*|cock(?:ed)? (?:it |that |this )?up|wank\w*|piss(?:ed)?)\b", re.I)),
    (4, re.compile(r"\b(?:bloody|damn\w*|hell|sod(?:s|ding)?|arse\w*|christ|god knows|kak|crap\w*|bugger\w*)\b", re.I)),
)
# Insults: the level a line needs before it may be said.
_INSULT = (
    (7, re.compile(r"\b(?:bastards?|pain in the arse|moron\w*|useless|pathetic|needy|bitch)\b|\byou absolute\b", re.I)),
    (4, re.compile(r"\b(?:muppets?|lazy|numpty|plonker|wally|idiots?|cheeky sod|filthy|sods?)\b", re.I)),
)
_SLANG = re.compile(r"\b(?:boet|lekker|eish|ag shame|jislaaik|yoh|ja nee|sharp sharp|now-now|kak|dop|howzit|bru)\b", re.I)
_MY_BRU = re.compile(r",?\s*\bmy bru\b,?", re.I)
_SLANG_ADDRESS = re.compile(r",?\s*\b(?:boet|bru)\b,?", re.I)
_SCRUB = re.compile(r"\b(?:bloody|fucking|effing|sodding|damn|bleeding)\s+", re.I)


class PersonalityError(ValueError):
    """The sliders sent from Settings were not valid."""


def _valid_set(value):
    return (isinstance(value, dict) and set(value) == set(TRAITS)
            and all(type(value[trait]) is int and MINIMUM <= value[trait] <= MAXIMUM for trait in TRAITS))


def _saved(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def listing(path=None):
    """Both slider sets, where each came from, the labels and the fingerprints."""
    saved = _saved(PATH if path is None else path)
    settings, sources = {}, {}
    for audience in AUDIENCES:
        if _valid_set(saved.get(audience)):
            settings[audience], sources[audience] = dict(saved[audience]), "saved"
        else:
            settings[audience], sources[audience] = dict(DEFAULTS[audience]), "default"
    return {"settings": settings, "sources": sources, "traits": list(TRAITS), "labels": dict(LABELS),
            "fingerprints": {audience: fingerprint(settings[audience]) for audience in AUDIENCES}}


def dials(audience="household", path=None):
    """The sliders for ``audience``. Any storage problem gives the defaults."""
    audience = audience if audience in AUDIENCES else "household"
    try:
        return listing(path)["settings"][audience]
    except (OSError, ValueError, KeyError, TypeError):
        return dict(DEFAULTS[audience])


def fingerprint(values):
    """Empty for the original personality (so lines learned before the sliders are kept)."""
    if not _valid_set(values) or values == BASE:
        return ""
    return "persona=" + "-".join(str(values[trait]) for trait in TRAITS)


def from_fingerprint(text):
    """The sliders a fingerprint stands for, or None for the original personality."""
    if not isinstance(text, str) or not text.startswith("persona="):
        return None
    parts = text.removeprefix("persona=").split("-")
    if len(parts) != len(TRAITS) or not all(part.isdigit() for part in parts):
        return None
    values = dict(zip(TRAITS, map(int, parts)))
    return values if _valid_set(values) else None


def save(payload, path=None, *, forget=None):
    """Save both slider sets. Returns the listing plus how many learned lines were forgotten.

    ``forget(keep)`` is called with the fingerprints still in use whenever a
    set changed; it defaults to line_freshness.forget_stale.
    """
    path = Path(PATH if path is None else path)
    if not isinstance(payload, dict) or set(payload) != set(AUDIENCES) or not all(
            _valid_set(payload[audience]) for audience in AUDIENCES):
        raise PersonalityError("Send whole numbers from 1 to 10 for sass, rudeness, humour, slang, chattiness, "
                               "swearing and insults, for both the household and guests.")
    before = listing(path)["settings"]
    clean = {audience: {trait: payload[audience][trait] for trait in TRAITS} for audience in AUDIENCES}
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(clean, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    result = listing(path)
    forgotten: int | None = 0
    if before != clean:
        if forget is None:
            from declan.turn import line_freshness
            forget = line_freshness.forget_stale
        try:
            forgotten = forget(set(result["fingerprints"].values()))
        except (OSError, ValueError, sqlite3.Error) as error:
            LOGGER.warning("Could not forget learned lines (%s); they stay until the next change",
                           type(error).__name__)
            forgotten = None
    result["forgotten"] = forgotten
    return result


# --- Who is listening -------------------------------------------------------

def note_guest_mode(state):
    """Record this turn's Guest Mode state (called by the HA reader)."""
    _GUEST_MODE.set(state)
    return state


def note_visitors(state):
    """Record this turn's visitor presence (called by the HA reader)."""
    _VISITORS.set(state)
    return state


def audience_for(guest_mode, visitors_present):
    """Same rule as the guest persona: Guest Mode not off, or visitors not known absent."""
    return "guests" if guest_mode != "off" or visitors_present is not False else "household"


def current_audience(fallback_guest=None):
    """The audience for this turn, from the states read so far.

    When nothing has been read yet, ``fallback_guest`` (True for guest wording)
    decides; with no hint it is the household.
    """
    guest_mode, visitors = _GUEST_MODE.get(), _VISITORS.get()
    if guest_mode is _UNSET and visitors is _UNSET:
        return "guests" if fallback_guest else "household"
    if guest_mode is _UNSET:
        return "guests" if visitors is not False else "household"
    if visitors is _UNSET:
        return "guests" if guest_mode != "off" else "household"
    return audience_for(guest_mode, visitors)


def audience_known():
    """Whether Guest Mode or visitor presence has been read this turn."""
    return _GUEST_MODE.get() is not _UNSET or _VISITORS.get() is not _UNSET


def reset_turn():
    _GUEST_MODE.set(_UNSET)
    _VISITORS.set(_UNSET)


# --- What the sliders do to wording ----------------------------------------

def gentle(values):
    """Low sass, rudeness and insults use the gentler (guest) line set."""
    return (values["sass"] + values["rudeness"] + values["insults"]) / 3 <= 3


def extra_line_chance(values):
    """Chance of adding a joke to a plain reply. The defaults give 1.0 (always)."""
    if values["chattiness"] <= 1:
        return 0.0
    return min(1.0, (values["sass"] + values["humour"]) / 14) * min(1.0, values["chattiness"] / 4)


def wants_extra_line(values, random=None):
    """Roll for an extra joke. Always True at the default sliders."""
    chance = extra_line_chance(values)
    if chance >= 1.0:
        return True
    if chance <= 0.0:
        return False
    return (random or _RANDOM).random() < chance  # nosec B311 - variety only


def max_words(values):
    """Longest line allowed for this chattiness (None means no limit)."""
    chattiness = values["chattiness"]
    if chattiness <= 1:
        return 8
    if chattiness <= 3:
        return 12
    return None


def _level(line, table):
    return max((level for level, pattern in table if pattern.search(line)), default=0)


def swear_level(line):
    return _level(line, _SWEAR)


def insult_level(line):
    return _level(line, _INSULT)


def _allowed_level(value):
    """1-3 allows nothing, 4-5 mild, 6-8 strong, 9-10 everything."""
    return 0 if value <= 3 else value


def shape(line, values):
    """The line as these sliders would say it, or None when they rule it out."""
    if not isinstance(line, str) or not line:
        return None
    text = line
    if values["slang"] <= 3:
        text = _tidy(_MY_BRU.sub("", text))
        if _SLANG.search(text):
            return None
    if swear_level(text) > _allowed_level(values["swearing"]):
        return None
    if insult_level(text) > _allowed_level(values["insults"]):
        return None
    limit = max_words(values)
    if limit is not None and len(text.split()) > limit:
        return None
    return text


def fixed(line, values=None):
    """A fixed sentence (not from a line pool) as the listener's sliders would say it."""
    if values is None:
        values = dials(current_audience())
    return shape(line, {**values, "chattiness": max(values["chattiness"], 4)}) or scrub(line, values)


def scrub(line, values):
    """Last resort when every line is ruled out: the tamest line, cleaned where it can be."""
    text = _SCRUB.sub("", line) if values["swearing"] <= 3 else line
    if values["slang"] <= 3:
        text = _SLANG_ADDRESS.sub("", _MY_BRU.sub("", text))
    return _tidy(text)


def excess(line, values):
    """How far a line goes past the sliders (0 = fine). Used to pick the tamest fallback."""
    return (max(0, swear_level(line) - _allowed_level(values["swearing"]))
            + max(0, insult_level(line) - _allowed_level(values["insults"])))


def _tidy(text):
    text = re.sub(r"\s+([,.!?;:])", r"\1", text)
    text = re.sub(r"([.!?])\s*[,;]", r"\1", text)
    text = re.sub(r"^[,;\s]+", "", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    # A sentence that now starts with a lower-case letter after a full stop.
    text = re.sub(r"([.!?]\s+)([a-z])", lambda found: found[1] + found[2].upper(), text)
    return text[:1].upper() + text[1:] if text else text


def _band(value, low, middle, high):
    return low if value <= 3 else middle if value <= 7 else high


def describe(values):
    """Plain-words persona for the AI, from the sliders."""
    parts = [
        _band(values["sass"], "Sass is low: warm and straightforward, very little sarcasm.",
              "Sass is moderate: dry and a bit sarcastic.",
              "Sass is high: very sarcastic, every reply has attitude."),
        _band(values["rudeness"], "Rudeness is low: courteous and patient.",
              "Rudeness is moderate: blunt and direct, not unkind.",
              "Rudeness is high: rude, impatient and unapologetically direct."),
        _band(values["humour"], "Humour is low: keep jokes rare.",
              "Humour is moderate: a joke now and then.",
              "Humour is high: always go for the laugh."),
        _band(values["slang"], "South African slang: none. Plain British English, never say 'my bru'.",
              "South African slang: some (for example my bru, lekker, eish, ag shame).",
              "South African slang: heavy (for example my bru, boet, lekker, eish, ag shame, jislaaik, yoh, "
              "ja nee, sharp sharp, now-now, kak)."),
        _band(values["swearing"], "Swearing: none at all.",
              "Swearing: mild only (bloody, damn, hell, arse)." if values["swearing"] <= 5
              else "Swearing: allowed, but not the strongest words.",
              "Swearing: anything goes."),
        _band(values["insults"], "Insults: none; never insult the listener.",
              "Insults: mild teasing only (muppet, lazy)." if values["insults"] <= 6
              else "Insults: cheeky, personal digs at the listener.",
              "Insults: savage, personal roasts of the listener."),
    ]
    return " ".join(parts)


def reply_length(values):
    """How long a spoken AI reply may be, for this chattiness."""
    chattiness = values["chattiness"]
    if chattiness <= 3:
        return "as short as possible: a few words or one short sentence, under 15 words"
    if chattiness <= 7:
        return "as short as possible: one sentence where you can, never more than two, under 30 words"
    return "chatty: up to three sentences, under 50 words"


def line_words(values):
    """Word limit for generated one-liners."""
    limit = max_words(values)
    if limit is not None:
        return limit
    return 28 if values["chattiness"] >= 8 else 18
