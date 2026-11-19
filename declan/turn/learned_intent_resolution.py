"""Resolve spoken self-corrections and learned intent aliases once per turn."""
import sqlite3


def resolve(message, *, preprocess, normalize, learned_intent, log_error):
    """Return the effective message and normalized phrase without alias chaining."""
    try:
        effective_message = preprocess(message).commands[0]
    except ValueError:
        effective_message = message
    phrase = normalize(effective_message)
    if len(phrase) <= 120:
        try:
            target = learned_intent(phrase)
        except (OSError, sqlite3.Error):
            log_error("Could not look up learned intention; using the original transcript.")
            target = None
        if isinstance(target, str) and 0 < len(target) <= 120:
            effective_message = target
            phrase = normalize(target)
    return effective_message, phrase
