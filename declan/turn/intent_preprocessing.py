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
# Speech-to-text (OpenAI in particular) keeps how people address Declan:
# "Declan, turn on the lights", "Okay Declan, play jazz", "Good night, Declan",
# "Pause the music, please". The address and courtesy words are not part of the
# command, so they are dropped before matching. "my bru" is kept: the command
# style setting relies on it.
_ADDRESS_LEAD = re.compile(
    r"^(?:(?:hey|hi|hello|ok|okay|howzit|yo)(?:\s*[,!.:]+\s*|\s+(?=declan\b)))?"
    r"(?:declan\b\s*[,!.:]*\s*)?",
    re.IGNORECASE,
)
_ADDRESS_TAIL = re.compile(
    r"(?:\s*,?\s*\b(?:declan|please|thanks|thank you)\b\s*[.!?]*)+$",
    re.IGNORECASE,
)


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
    text = _without_address(text)
    if not text:
        raise ValueError("Speech contains no usable command")
    return ParsedSpeech((text,), corrected)


def _without_address(text: str) -> str:
    """Drop "Declan," / "Hey," and a trailing ", Declan" or "please".

    The original is kept when fewer than two words would remain, so greetings
    ("hello Declan"), "good night Declan" style phrases that are matched as a
    whole elsewhere, and one-word replies ("yes please") keep their meaning.
    """
    stripped = _ADDRESS_TAIL.sub("", _ADDRESS_LEAD.sub("", text, count=1)).strip(" ,.;:!")
    return stripped if len(stripped.split()) >= 2 else text


# Polite request wrappers around an ordinary command ("can you turn on the office
# light please"). Only the wrapper is removed; the command itself is untouched.
_POLITE_LEAD = re.compile(
    r"^(?:please,? )?(?:(?:can|could|would|will) you(?:,? please)?,? |please,? )"
)
_MIND_LEAD = re.compile(r"^(?:please,? )?(?:would|do) you mind (\w+) ")
_POLITE_TAIL = re.compile(r"(?:,? (?:please|thanks|thank you|my bru|for me))+$")
_GERUNDS = {
    "turning": "turn", "switching": "switch", "playing": "play", "setting": "set",
    "dimming": "dim", "brightening": "brighten", "starting": "start", "stopping": "stop",
    "running": "run", "opening": "open", "closing": "close", "putting": "put",
    "making": "make", "pausing": "pause", "skipping": "skip", "cancelling": "cancel",
    "canceling": "cancel",
}


def strip_polite_request(phrase: str) -> str:
    """Return a normalised phrase without a polite request wrapper.

    Input must already be normalised (lower case, single spaces). Returns the
    phrase unchanged when no wrapper is present or under two words would remain, so
    plain commands, questions and unknown phrasing are never altered.
    """
    if not isinstance(phrase, str):
        return phrase
    command = _POLITE_TAIL.sub("", phrase)
    mind = _MIND_LEAD.match(command)
    if mind:
        verb = _GERUNDS.get(mind.group(1))
        command = verb + command[mind.end() - 1:] if verb else command
    else:
        command = _POLITE_LEAD.sub("", command, count=1)
    command = command.strip(" ,")
    # A one-word remainder ("yes please", "stop please") is left as spoken, so
    # confirmation replies and bare Stop keep their existing exact-match meaning.
    return command if len(command.split()) >= 2 else phrase
