"""One-shot, origin-bound voice confirmation for sensitive household routines."""
import os
import sqlite3
from threading import Lock
from time import monotonic
from confirmation_results import ConfirmationDecision, ConfirmationEvaluation

YES = {"yes", "yes confirm", "confirm", "go ahead", "do it"}
NO = {"no", "cancel", "never mind", "don't", "stop"}
DEFAULT_GROUPS = {"night", "guest"}
DEFAULT_TRUSTED: set[str] = set()
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
            and isinstance(confidence, (int, float)) and type(confidence) in (int, float) and 0.85 <= confidence <= 1.0)


def _mapped_sensitive(name):
    try:
        import routine_registry
        return routine_registry.load().get(name, {}).get("sensitive") is True
    except (ValueError, OSError, sqlite3.Error):
        return True


def sensitive_group(phrase, routine, guest_commands, sexy_commands=None, dinner_phrases=None):
    if phrase in guest_commands and guest_commands[phrase] != "check":
        return "guest"
    if sexy_commands and phrase in sexy_commands:
        return "custom:sexy_time" if _mapped_sensitive("sexy_time") else "sexy"
    if dinner_phrases and phrase in dinner_phrases:
        return "custom:dinner" if _mapped_sensitive("dinner") else "dinner"
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
        # An explicitly saved routine policy overrides legacy group defaults.
        # In particular, an unchecked Good Night confirmation box must not
        # be silently re-enabled by DECLAN_SENSITIVE_ROUTINES=night.
        if group in {"night", "morning", "movie", "movie_bedroom"} and item:
            return None
        return group
    if phrase.startswith(("good night", "goodnight", "time for bed", "shut the house down")):
        try:
            import routine_registry
            mapped = routine_registry.load().get("night")
        except (ValueError, OSError, sqlite3.Error):
            return "night"
        if mapped:
            return "custom:night" if mapped["sensitive"] else None
        return "night"
    return None


class ConfirmationGate:
    def __init__(self, clock=monotonic):
        self.clock = clock
        self.lock = Lock()
        self.pending = {}

    def evaluate(self, *, session, origin, phrase, group, speaker):
        """Compatibility API retaining plain decision/phrase pairs."""
        result = self.evaluate_result(session=session, origin=origin, phrase=phrase, group=group, speaker=speaker)
        return result.decision.value, result.approved_phrase

    def evaluate_result(self, *, session, origin, phrase, group, speaker):
        """Return a typed one-shot decision bound to session and origin."""
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
                    return ConfirmationEvaluation(ConfirmationDecision.CANCELLED)
                return ConfirmationEvaluation(ConfirmationDecision.CONFIRMED, existing["phrase"])
            if phrase in YES | NO:
                return ConfirmationEvaluation(ConfirmationDecision.ALLOW)
            if not group or (not group.startswith("custom:") and group not in groups()):
                return ConfirmationEvaluation(ConfirmationDecision.ALLOW)
            if not session or not origin:
                return ConfirmationEvaluation(ConfirmationDecision.DENIED)
            self.pending[key] = {"phrase": phrase, "expires": now + TTL_SECONDS}
            return ConfirmationEvaluation(ConfirmationDecision.PROMPT)
