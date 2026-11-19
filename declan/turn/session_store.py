"""Single owner for mutable conversation session state."""
from collections import OrderedDict
from dataclasses import dataclass, field
from threading import Lock
from declan.turn.chat_recall_memory import ChatRecallMemory


@dataclass
class SessionStore:
    """Own session entries and their shared lock as one injectable dependency."""

    sessions: OrderedDict = field(default_factory=OrderedDict)
    lock: Lock = field(default_factory=Lock)
    chat_recall: ChatRecallMemory = field(default_factory=ChatRecallMemory)


DEFAULT_SESSION_STORE = SessionStore()
