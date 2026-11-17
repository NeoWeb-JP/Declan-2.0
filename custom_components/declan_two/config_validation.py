"""Validation helpers for Home Assistant configuration."""
from urllib.parse import urlsplit


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
