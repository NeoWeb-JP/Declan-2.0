"""One-shot, origin-bound voice confirmation for sensitive household routines."""
import os
import re
import sqlite3
from threading import Lock
from time import monotonic

YES = {"yes", "yes confirm", "confirm", "go ahead", "do it"}
NO = {"no", "cancel", "never mind", "don't", "stop"}
DEFAULT_GROUPS = {"night", "guest"}
DEFAULT_TRUSTED = set()
TTL_SECONDS = 30


def groups():
    raw = os.environ.get("DECLAN_SENSITIVE_ROUTINES", "night,guest")
    return {x.strip().casefold() for x in raw.split(",") if x.strip()}


def trusted_speaker(speaker):
    if not isinstance(speaker, dict):
        return False
    name = speaker.get("name")
    confidence = speaker.get("confidence")
    allowed = {x.strip().casefold() for x in os.environ.get("DECLAN_TRUSTED_SPEAKERS", "").split(",") if x.strip()}
    return (isinstance(name, str) and bool(name.strip()) and name.strip().casefold() in allowed
            and type(confidence) in (int, float) and 0.85 <= confidence <= 1.0)


def sensitive_group(phrase, routine, guest_commands, sexy_commands=None, dinner_phrases=None):
    if phrase in guest_commands and guest_commands[phrase] != "check":
        return "guest"
    if sexy_commands and phrase in sexy_commands:
        return "sexy"
    if dinner_phrases and phrase in dinner_phrases:
        return "dinner"
    if routine:
        group = routine[0][0]
        if group.startswith("custom:"):
            import routine_registry
            try:
                item = routine_registry.load().get(group[7:])
            except (ValueError, OSError, sqlite3.Error):
                return group
            return group if item and item["sensitive"] else None
        try:
            import routine_registry
            item = routine_registry.load().get(group)
            if item and item["sensitive"]:
                return "custom:" + group
        except (ValueError, OSError, sqlite3.Error):
            return "custom:" + group
        return group
    if phrase.startswith(("good night", "goodnight", "time for bed", "shut the house down")):
        return "night"
    return None


class ConfirmationGate:
    def __init__(self, clock=monotonic):
        self.clock = clock
        self.lock = Lock()
        self.pending = {}

    def evaluate(self, *, session, origin, phrase, group, speaker):
        """Return (decision, phrase): allow, prompt, confirmed, cancelled, denied."""
        now = self.clock()
        with self.lock:
            for key, item in list(self.pending.items()):
                if now >= item["expires"]:
                    del self.pending[key]
            key = (session, origin)
            existing = self.pending.get(key)
            if existing and phrase in YES | NO:
                del self.pending[key]
                if phrase in NO:
                    return "cancelled", None
                return "confirmed", existing["phrase"]
            if phrase in YES | NO:
                return "allow", None
            if not group or (not group.startswith("custom:") and group not in groups()):
                return "allow", None
            if not session or not origin:
                return "denied", None
            self.pending[key] = {"phrase": phrase, "expires": now + TTL_SECONDS}
            return "prompt", None
