"""Identify eligible routine preview requests without executing actions."""
import re


_PREVIEW_PREFIX = re.compile(r"^(?:preview|dry[ -]run)\b[ ,:]*")
_LIGHTING_WORDS = re.compile(r"\b(?:light|lights|lamp|spotlight|brightness|dim|switch)\b")


def routine_preview_phrase(phrase):
    """Return a routine preview target, or None when preview is ineligible."""
    match = _PREVIEW_PREFIX.match(phrase)
    candidate = phrase[match.end():] if match else None
    if candidate and not _LIGHTING_WORDS.search(candidate):
        return candidate
    return None
