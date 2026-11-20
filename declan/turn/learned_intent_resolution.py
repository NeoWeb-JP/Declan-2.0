"""Resolve spoken self-corrections and learned intent aliases once per turn."""
import sqlite3

from declan.turn.intent_preprocessing import strip_polite_request


def resolve(message, *, preprocess, normalize, learned_intent, log_error,
            polite=strip_polite_request):
    """Return the effective message and normalized phrase without alias chaining.

    A learned phrase is looked up as spoken first, then without a polite request
    wrapper ("can you ... please"). Local parsers receive the unwrapped command;
    the effective message (used by the AI fallback and history) stays as spoken.
    """
    try:
        effective_message = preprocess(message).commands[0]
    except ValueError:
        effective_message = message
    phrase = normalize(effective_message)
    candidates = [phrase]
    plain = polite(phrase)
    if isinstance(plain, str) and plain and plain != phrase:
        candidates.append(plain)
    for candidate in candidates:
        if len(candidate) > 120:
            continue
        try:
            target = learned_intent(candidate)
        except (OSError, sqlite3.Error):
            log_error("Could not look up learned intention; using the original transcript.")
            break
        if isinstance(target, str) and 0 < len(target) <= 120:
            return target, normalize(target)
    return effective_message, candidates[-1]
