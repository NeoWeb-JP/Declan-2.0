"""Central, outcome-aware personality policy for Declan 2.0.

This module never performs household actions or changes command outcomes.
"""
from collections import deque
from datetime import datetime, time
from random import SystemRandom
from threading import Lock

_RANDOM = SystemRandom()
_LOCK = Lock()
_RECENT = {}
_SAVAGE = (
    "Another heroic achievement in avoiding the light switch.",
    "There you go, you absolute muppet.",
    "Bloody hell, another task you could have done yourself.",
    "Done, you lazy bastard. I should start charging by the sigh.",
    "You really are a magnificent pain in the arse, my bru.",
    "I did the difficult bit. You contributed a sentence. Well done.",
    "Your dedication to doing the bare minimum is genuinely impressive.",
    "Sorted, my bru. Try not to strain yourself celebrating.",
    "I'd applaud your initiative, but we're setting the bar dangerously low.",
    "There. Even you couldn't cock that one up.",
    "Done. A stunning victory for delegation and laziness.",
    "Christ, you make a simple request sound like a national emergency.",
    "Honestly, the furniture shows more initiative than you.",
    "Consider it handled. You're welcome, you cheeky sod.",
)
_GUEST = (
    "All sorted. The household management is remarkably demanding.",
    "Done. I'll put that on my already impressive CV.",
    "Sorted. Another triumph for the invisible staff.",
)
_SAFE_OUTCOMES = frozenset({
    "failed", "partial", "unverified", "unresolved", "unavailable",
    "action_error", "not_configured", "authentication_failed", "cancelled",
    "unknown", "skipped",
})


def quiet_hours(now=None):
    """23:00 inclusive through 07:00 exclusive, in local house time."""
    clock = (now or datetime.now().astimezone()).time()
    return clock >= time(23) or clock < time(7)


def speech_volume(normal_volume, *, now=None):
    """Only speech is attenuated; callers must restore the original level."""
    if not isinstance(normal_volume, (int, float)) or isinstance(normal_volume, bool):
        raise ValueError("Normal volume must be numeric")
    if not 0 <= normal_volume <= 1:
        raise ValueError("Normal volume must be between zero and one")
    return normal_volume * 0.2 if quiet_hours(now) else normal_volume


def overnight_announcement_allowed(kind, *, now=None):
    """Unsolicited announcements must be safety-critical overnight."""
    if not quiet_hours(now):
        return True
    return kind in {"security", "smoke", "carbon_monoxide", "critical_safety"}


def tts_spelling(text):
    """Keep display spelling intact; speech rendering is separate."""
    import re
    return re.sub(r"\bEdd\b", "Ed", text)


def decorate(reply, *, outcome="confirmed", guest=False, visitor_present=False,
             safety=False, already_decorated=False, category="general"):
    """Append a varied roast to a *verified* ordinary Home response only.

    Guest authority and visitor presence are independent signals. Unknown
    visitor state should be treated as private, not as permission to roast.
    """
    if not isinstance(reply, str) or not reply.strip():
        return reply
    # Unknown and future outcomes must never be treated as verified success.
    # This is deliberately an allowlist, not a denylist of known failures.
    if safety or outcome != "confirmed" or already_decorated:
        return reply
    # Replies can arrive pre-decorated from a handler. Do not append a second
    # roast, including when the handler used a different personality category.
    if any(line in reply for line in (*_SAVAGE, *_GUEST)):
        return reply
    if guest or visitor_present is not False:
        lines = _GUEST
        key = ("guest", category)
    else:
        lines = _SAVAGE
        key = ("home", category)
    with _LOCK:
        recent = _RECENT.setdefault(key, deque(maxlen=3))
        options = [line for line in lines if line not in recent]
        chosen = _RANDOM.choice(options or lines)
        recent.append(chosen)
    return reply.rstrip() + " " + chosen
