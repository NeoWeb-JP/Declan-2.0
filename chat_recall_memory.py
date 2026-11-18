"""Bounded in-memory chat recall, separate from safety-critical action context."""

from collections import OrderedDict
from dataclasses import dataclass, field

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
            if now - value["at"] >= RECALL_SECONDS:
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
        self.entries.move_to_end(session_id)
        return {"name": previous["name"], "last": previous["last"],
                "recent_messages": list(previous["recent_messages"])}

    def remember(self, session_id, state, now):
        if not isinstance(session_id, str) or not session_id:
            return
        self.prune(now)
        name = state.get("name")
        name = name[:40] if isinstance(name, str) else None
        messages = state.get("recent_messages", [])
        messages = [
            item[:MAX_MESSAGE_CHARACTERS] for item in messages[-MAX_RECENT_MESSAGES:]
            if isinstance(item, str)
        ]
        last = state.get("last")
        self.entries[session_id] = {
            "at": now, "name": name,
            "last": last[:MAX_MESSAGE_CHARACTERS] if isinstance(last, str) else None,
            "recent_messages": tuple(messages),
        }
        self.entries.move_to_end(session_id)
        self.prune(now)

    def forget(self, session_id):
        self.entries.pop(session_id, None)
