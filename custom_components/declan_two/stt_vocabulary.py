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
    if not isinstance(value, str) or len(value) > MAX_LENGTH:
        raise ValueError("Enter up to 12 short comma-separated vocabulary terms.")
    if not value.strip():
        return ""
    terms = [part.strip() for part in value.split(",")]
    if (len(terms) > MAX_TERMS or any(not TERM.fullmatch(term) for term in terms)):
        raise ValueError("Enter simple comma-separated words, names or room labels.")
    return ", ".join(terms)


def prompt(vocabulary):
    """No household-specific names are sent unless explicitly configured."""
    try:
        words = validate_vocabulary(vocabulary)
    except ValueError:
        words = ""
    return DEFAULT_PROMPT + (" Vocabulary: " + words + "." if words else "")
