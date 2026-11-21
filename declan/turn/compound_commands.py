"""Conservative splitting of one lighting command joined to one music command (#300).

Only a lighting + music pair is split, in either order, and only when each half
is independently recognised by its own parser. Everything else (for example
"turn on the kitchen and dining lights" or "play rock in the kitchen and lounge")
is left whole, so a conjunction inside a target is never mistaken for a second
command. No side effects: the caller dispatches each half.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from declan.core.execution_results import Outcome

# "and", ", and", "and then", ", then". Longest alternatives first.
_JOINER = re.compile(r"\s*,?\s+and then\s+|\s*,\s*then\s+|\s*,?\s+and\s+")
# A pronoun or preview form depends on conversation context; never split those.
_CONTEXTUAL = re.compile(r"\b(?:it|them|that|those)\b|^(?:preview|dry[ -]run)\b")

_SUCCESS = frozenset({
    Outcome.CONFIRMED, Outcome.STARTED, Outcome.REQUESTED,
    Outcome.REPORTED_SUCCESS, Outcome.EXECUTION_COMPLETED,
})


@dataclass(frozen=True)
class CompoundSplit:
    first: str
    second: str


def split_lighting_and_music(phrase, *, parse_music, is_lighting):
    """Return the two halves in spoken order, or None to keep the phrase whole.

    A split needs exactly one music half (starting with "play" and accepted by
    parse_music) and one lighting half (accepted by is_lighting). If more than
    one boundary qualifies, nothing is split rather than guessing.
    """
    if not isinstance(phrase, str) or len(phrase) > 512:
        return None
    candidates = []
    for joiner in _JOINER.finditer(phrase):
        left = phrase[:joiner.start()].strip(" ,")
        right = phrase[joiner.end():].strip(" ,")
        if not left or not right:
            continue
        for music_half, light_half in ((left, right), (right, left)):
            if (music_half.startswith("play ") and not _CONTEXTUAL.search(light_half)
                    and _safe(parse_music, music_half) and _safe(is_lighting, light_half)):
                candidates.append(CompoundSplit(left, right))
                break
    return candidates[0] if len(candidates) == 1 else None


def _safe(check, text):
    try:
        return bool(check(text))
    except (ValueError, TypeError):
        return False


def combined_outcome(first, second):
    """Combine two independent results without hiding a failure behind a success."""
    outcomes = [Outcome(value) for value in (first, second) if value is not None]
    if not outcomes:
        return None
    if len(outcomes) == 1:
        # One half matched nothing at all: never report the pair as complete.
        return Outcome.PARTIAL if outcomes[0] in _SUCCESS else outcomes[0]
    a, b = outcomes
    if a in _SUCCESS and b in _SUCCESS:
        if a is b:
            return a
        # Both succeeded, but one is weaker evidence (e.g. requested, not confirmed).
        return a if a is not Outcome.CONFIRMED else b
    if a in _SUCCESS or b in _SUCCESS:
        return Outcome.PARTIAL
    if Outcome.UNVERIFIED in (a, b):
        return Outcome.UNVERIFIED
    return a if a is b else Outcome.FAILED


def combined_reply(first, second):
    parts = [part.strip() for part in (first, second) if isinstance(part, str) and part.strip()]
    return " ".join(parts) if parts else None


# FUT-59: several cooking timers in one sentence ("set a turkey timer for 3 hours
# and a roast potatoes timer for 50 minutes", "turkey 3 hours, roast potatoes 50
# minutes"). Only split when every piece is a named timer with a valid duration.
_TIMER_LEAD = re.compile(r"^(?:(?:please )?(?:set|start) (?:(?:the|some|two|three|four) )?(?:timers?|alarms?)?\s*(?:for|:)?\s*|"
                         r"timers?\s*(?:for|:)\s*|set\s+)")
_TIMER_JOIN = re.compile(r"\s*,\s*(?:and\s+)?|\s+and\s+|\s*;\s*")
_DURATION = r"(?P<duration>(?:(?:a|an|one|half an?)\s+)?[\w -]+?\s+(?:hours?|hrs?|minutes?|mins?|seconds?|secs?)(?:\s+and\s+[\w -]+?\s+(?:minutes?|mins?|seconds?|secs?))?)"
_TIMER_FORMS = (
    re.compile(rf"(?:(?:a|an|the)\s+)?(?P<name>[a-z][a-z' ]{{0,40}}?)\s+timer\s+for\s+{_DURATION}"),
    re.compile(rf"(?:(?:a|an)\s+)?timer\s+for\s+{_DURATION}\s+(?:for|called|on)\s+(?:the\s+)?(?P<name>[a-z][a-z' ]{{0,40}})"),
    re.compile(rf"{_DURATION}\s+(?:for|on)\s+(?:the\s+)?(?P<name>[a-z][a-z' ]{{0,40}})"),
)
_NAME = re.compile(r"(?:the\s+)?([a-z][a-z' ]{0,40})")


def _timer_piece(text, duration_seconds):
    def usable(name, duration):
        name = name.strip()
        return (name and not name.startswith(("timer", "a timer")) and duration_seconds(name) is None
                and duration_seconds(duration) is not None)
    for form in _TIMER_FORMS:
        found = form.fullmatch(text)
        if found and usable(found["name"], found["duration"]):
            return found["name"].strip(), found["duration"].strip()
    # "turkey 3 hours", "roast potatoes for 50 minutes": try each split point.
    words = text.split()
    for cut in range(1, len(words)):
        name, duration = " ".join(words[:cut]), " ".join(words[cut:])
        duration = duration.removeprefix("for ")
        named = _NAME.fullmatch(name)
        if named and usable(named[1], duration):
            return named[1].strip(), duration
    return None


def split_timers(phrase, *, duration_seconds):
    """Return one "set a <name> timer for <duration>" command per timer, or None."""
    if not isinstance(phrase, str) or len(phrase) > 512 or not re.search(r"\b(?:hours?|minutes?|mins?|seconds?|secs?|hrs?)\b", phrase):
        return None
    text = _TIMER_LEAD.sub("", phrase.strip().casefold())
    pieces = [piece.strip() for piece in _TIMER_JOIN.split(text) if piece.strip()]
    timers: list[tuple[str, str]] = []
    for piece in pieces:
        parsed = _timer_piece(piece, duration_seconds)
        if parsed:
            timers.append(parsed)
            continue
        # "1 hour and 30 minutes" was split at its "and": rejoin it to the previous timer.
        if timers and duration_seconds(timers[-1][1] + " and " + piece) is not None:
            timers[-1] = (timers[-1][0], timers[-1][1] + " and " + piece)
            continue
        return None
    if len(timers) < 2 or len(timers) > 6:
        return None
    return [f"set a {name} timer for {duration}" for name, duration in timers]
