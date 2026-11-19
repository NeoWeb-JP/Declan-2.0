"""Conservative speech-intent preprocessing.

No side effects, HA calls, or model calls are permitted here. The caller must
validate every returned command before execution. Ambiguity is left intact
for the interpreter rather than guessing which device to operate.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_CORRECTION = re.compile(
    r"\b(?:no\s*,?\s*(?:i mean|actually)|actually\s*,?\s*i meant|"
    r"i mean|sorry\s*,?\s*i meant|scratch that)\s*[,.:]?\s*",
    re.IGNORECASE,
)
_FILLER = re.compile(r"\b(?:um+|uh+|erm+)\b", re.IGNORECASE)
_SPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class ParsedSpeech:
    commands: tuple[str, ...]
    corrected: bool = False


def preprocess_speech(text: str, *, max_length: int = 2048) -> ParsedSpeech:
    """Return conservative candidate commands, never executable actions.

    Corrections supersede the preceding utterance in full. Conjunctions are
    deliberately NOT split here: 'turn on the kitchen and dining lights'
    must not be mistaken for two independent actions. An LLM or validated
    local parser must resolve multi-action dependencies later.
    """
    if not isinstance(text, str) or not 0 < len(text) <= max_length:
        raise ValueError("Speech text is missing or exceeds the limit")
    matches = list(_CORRECTION.finditer(text))
    corrected = bool(matches)
    if matches:
        text = text[matches[-1].end():]
    text = _SPACE.sub(" ", _FILLER.sub(" ", text)).strip(" ,.;:")
    if not text:
        raise ValueError("Speech contains no usable command")
    return ParsedSpeech((text,), corrected)
