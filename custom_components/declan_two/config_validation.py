"""Validation helpers for Home Assistant configuration."""
from urllib.parse import urlsplit
from dataclasses import dataclass
from enum import StrEnum


class TokenVerificationStatus(StrEnum):
    VALID = "valid"
    INVALID_AUTH = "invalid_auth"
    CANNOT_CONNECT = "cannot_connect"


@dataclass(frozen=True)
class TokenVerificationResult:
    status: TokenVerificationStatus

    def __post_init__(self):
        if not isinstance(self.status, TokenVerificationStatus):
            raise TypeError("status must be a TokenVerificationStatus")

    def form_error(self) -> str | None:
        return None if self.status is TokenVerificationStatus.VALID else self.status.value


def valid_declan_origin(url: str) -> bool:
    """Accept only HTTP(S) origins, not URLs with paths or embedded credentials."""
    try:
        parsed = urlsplit(url)
        return bool(
            parsed.scheme in {"http", "https"}
            and parsed.hostname
            and parsed.path in {"", "/"}
            and not any((parsed.username, parsed.password, parsed.query, parsed.fragment))
            and parsed.port != 0
        )
    except ValueError:
        return False
