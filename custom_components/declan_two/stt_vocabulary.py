"""Opt-in, bounded vocabulary hints for Declan's Home Assistant OpenAI STT."""

import re

DEFAULT_PROMPT = (
    "Home Assistant voice commands, room names, lighting, timers, routines, "
    "media playback and music requests."
)
TERM = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._'\-]{0,39}\Z")
MAX_TERMS = 12
MAX_LENGTH = 240


def validate_vocabulary(value):
    """Allow short comma-separated terms, never arbitrary instruction prompts."""
    if (not isinstance(value, str) or len(value) > MAX_LENGTH
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
            or re.search(r"\b(?:ignore|instructions|override|execute|prompt)\b", value, re.I)):
        raise ValueError("Enter up to 12 short comma-separated vocabulary terms.")
    if not value.strip():
        return ""
    terms = [part.strip() for part in value.split(",")]
    if (len(terms) > MAX_TERMS or any(not TERM.fullmatch(term) for term in terms)):
        raise ValueError("Enter simple comma-separated words, names or room labels.")
    return ", ".join(terms)


FIXED_NAMES = ("Declan", "Howzit Declan", "my bru")
MAX_AUTO_TERMS = 40
MAX_AUTO_LENGTH = 500


def automatic_terms(names):
    """Bounded, cleaned household names (rooms, exposed devices). Opt-in only."""
    terms: list[str] = []
    seen: set[str] = set()
    length = 0
    for name in (*FIXED_NAMES, *names):
        if not isinstance(name, str):
            continue
        term = " ".join(re.sub(r"[^A-Za-z0-9 ._'\-]", " ", name).split())[:40]
        key = term.casefold()
        if not term or key in seen or not TERM.fullmatch(term) or re.search(
                r"\b(?:ignore|instructions|override|execute|prompt)\b", term, re.IGNORECASE):
            continue
        if len(terms) >= MAX_AUTO_TERMS or length + len(term) + 2 > MAX_AUTO_LENGTH:
            break
        terms.append(term)
        seen.add(key)
        length += len(term) + 2
    return terms


def prompt(vocabulary, automatic=()):
    """No household-specific names are sent unless explicitly configured or opted in."""
    try:
        words = validate_vocabulary(vocabulary)
    except ValueError:
        words = ""
    text = DEFAULT_PROMPT + (" Vocabulary: " + words + "." if words else "")
    manual = {term.strip().casefold() for term in words.split(",") if term.strip()}
    names = [term for term in automatic if term.casefold() not in manual]
    return text + (" Names: " + ", ".join(names) + "." if names else "")
