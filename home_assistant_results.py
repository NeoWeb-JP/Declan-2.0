"""Home Assistant connection health has its own non-execution vocabulary."""
from dataclasses import dataclass
from enum import StrEnum


class HomeAssistantStatus(StrEnum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    AUTHENTICATION_FAILED = "authentication_failed"
    NOT_CONFIGURED = "not_configured"
    ASSIST_RECENT = "assist_recent"


@dataclass(frozen=True)
class HomeAssistantStatusResult:
    status: HomeAssistantStatus

    def __post_init__(self):
        if not isinstance(self.status, HomeAssistantStatus):
            raise TypeError("status must be a HomeAssistantStatus")
