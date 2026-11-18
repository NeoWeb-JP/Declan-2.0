"""Bounded in-memory chat recall, separate from safety-critical action context."""

from collections import OrderedDict
from dataclasses import dataclass, field
from math import isfinite
from chat_recall_privacy import safe_chat_text

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
        for key, value in list(self.entries.items()):
            at = value.get("at") if isinstance(value, dict) else None
            if (type(at) not in (int, float) or not isfinite(at)
                    or at > now or now - at >= RECALL_SECONDS):
                self.entries.pop(key, None)
        while len(self.entries) > MAX_SESSIONS:
            self.entries.popitem(last=False)

    def restore(self, session_id, now):
        self.prune(now)
        if not isinstance(session_id, str):
            return None
        previous = self.entries.get(session_id)
        if previous is None:
            return None
        # Reject malformed entries instead of restoring unsafe or partial state.
        if (not isinstance(previous.get("recent_messages"), (tuple, list))
                or not isinstance(previous.get("last"), str)):
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
        if not isinstance(session_id, str) or not session_id:
            return
        self.prune(now)
        if not isinstance(state, dict):
            return
        name = state.get("name")
        # Names are spoken back on request; apply the same privacy boundary.
        name = safe_chat_text(name)
        name = name[:40] if name is not None else None
        messages = state.get("recent_messages", [])
        if not isinstance(messages, (list, tuple)):
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
        self.entries.pop(session_id, None)
