"""Validate typed music provider results and legacy injected reply pairs."""
from declan.core.execution_results import ExecutionResult
from dataclasses import dataclass
from enum import StrEnum


class MusicFailureKind(StrEnum):
    RATE_LIMITED = "rate_limited"
    SERVICE_UNAVAILABLE = "service_unavailable"
    HTTP_ERROR = "http_error"
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class MusicRequestFailure:
    kind: MusicFailureKind
    http_status: int | None = None

    def __post_init__(self):
        if not isinstance(self.kind, MusicFailureKind):
            raise TypeError("kind must be a MusicFailureKind")
        if self.http_status is not None and type(self.http_status) is not int:
            raise TypeError("HTTP status must be an integer or None")

    @classmethod
    def from_http_status(cls, status) -> "MusicRequestFailure":
        kind = (MusicFailureKind.RATE_LIMITED if status == 429 else
                MusicFailureKind.SERVICE_UNAVAILABLE if status in {502, 503, 504} else MusicFailureKind.HTTP_ERROR)
        return cls(kind, status)


class PlayerAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class PlayerAvailabilityResult:
    status: PlayerAvailability

    def __post_init__(self):
        if not isinstance(self.status, PlayerAvailability):
            raise TypeError("status must be a PlayerAvailability")

    @property
    def available(self) -> bool:
        return self.status is PlayerAvailability.AVAILABLE


def music_execution_result(provider_reply):
    """Validate a provider reply and return a frozen typed execution result."""
    if isinstance(provider_reply, ExecutionResult):
        return provider_reply
    if type(provider_reply) not in (tuple, list) or len(provider_reply) != 2:
        raise ValueError("Music provider must return a reply/outcome pair")
    return ExecutionResult(*provider_reply)
