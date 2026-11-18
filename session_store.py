"""Single owner for mutable conversation session state."""
from collections import OrderedDict
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class SessionStore:
    """Own session entries and their shared lock as one injectable dependency."""

    sessions: OrderedDict = field(default_factory=OrderedDict)
    lock: Lock = field(default_factory=Lock)


DEFAULT_SESSION_STORE = SessionStore()
