"""Bounded in-memory chat recall, separate from safety-critical action context."""

from collections import OrderedDict
from dataclasses import dataclass, field
from context_numeric_validation import finite_number
from declan.turn.session_identity import valid_session_id
from declan.turn.chat_recall_privacy import safe_chat_text

MAX_SESSIONS = 128
MAX_MESSAGE_CHARACTERS = 160
MAX_RECENT_MESSAGES = 3
RECALL_SECONDS = 1800


@dataclass
class ChatRecallMemory:
    """Caller synchronises access with its existing session-store lock.

    Never persist transcripts to disk or restore action/confirmation metadata.
    """
    entries: OrderedDict = field(default_factory=OrderedDict)

    def prune(self, now):
        if not finite_number(now):
            self.entries.clear()
            return
        for key, value in list(self.entries.items()):
            at = value.get("at") if type(value) is dict else None
            if (not valid_session_id(key) or not finite_number(at)
                    or at > now or now - at >= RECALL_SECONDS):
                self.entries.pop(key, None)
        while len(self.entries) > MAX_SESSIONS:
            self.entries.popitem(last=False)

    def restore(self, session_id, now):
        self.prune(now)
        if not valid_session_id(session_id):
            return None
        previous = self.entries.get(session_id)
        if type(previous) is not dict:
            self.entries.pop(session_id, None)
            return None
        # Reject malformed entries instead of restoring unsafe or partial state.
        if (type(previous.get("recent_messages")) not in (tuple, list)
                or type(previous.get("last")) is not str):
            self.entries.pop(session_id, None)
            return None
        last = safe_chat_text(previous["last"])
        if last is None:
            # A legacy or corrupted entry must not become a repeatable secret.
            self.entries.pop(session_id, None)
            return None
        name = safe_chat_text(previous.get("name"))
        self.entries.move_to_end(session_id)
        return {"name": name[:40] if name is not None else None,
                "last": last,
                "recent_messages": [safe for item in previous["recent_messages"]
                                    if (safe := safe_chat_text(item)) is not None][-MAX_RECENT_MESSAGES:]}

    def remember(self, session_id, state, now):
        if not valid_session_id(session_id) or not finite_number(now):
            return
        self.prune(now)
        if type(state) is not dict:
            return
        name = state.get("name")
        # Names are spoken back on request; apply the same privacy boundary.
        name = safe_chat_text(name)
        name = name[:40] if name is not None else None
        messages = state.get("recent_messages", [])
        if type(messages) not in (list, tuple):
            messages = []
        messages = [text for item in messages
                    if (text := safe_chat_text(item)) is not None][-MAX_RECENT_MESSAGES:]
        last = safe_chat_text(state.get("last"))
        if last is None:
            # A rejected utterance must not refresh the lifetime of older chat.
            # Keep the previous entry untouched until it naturally expires.
            return
        self.entries[session_id] = {
            "at": now, "name": name, "last": last,
            "recent_messages": tuple(messages),
        }
        self.entries.move_to_end(session_id)
        self.prune(now)

    def forget(self, session_id):
        if valid_session_id(session_id):
            self.entries.pop(session_id, None)
