"""Conservative privacy boundary for ephemeral conversation recall.

This is not a general secret detector. Favour forgetting an uncertain command
over replaying a private instruction half an hour later.
"""

import re

# Credential-like phrases, identity numbers and instructions must not be
# repeated from a chat-memory buffer. The ordinary five-minute conversation
# state has a separate safety/retention policy.
_SENSITIVE = re.compile(
    r"(?i)\b(?:password|passcode|passphrase|pin(?:\s+code)?|secret|"
    r"api[ _-]?key|access[ _-]?token|bearer|authentication|"
    r"credential|private[ _-]?key|recovery[ _-]?code|"
    r"bank[ _-]?account|sort[ _-]?code|card[ _-]?number|"
    r"security[ _-]?code|one[ _-]?time[ _-]?code)\b"
)
_ACTION = re.compile(
    r"(?i)\b(?:turn\s+(?:on|off)|switch\s+(?:on|off)|"
    r"set\s+(?:the\s+)?(?:light|lamp|thermostat|temperature|fan|alarm)|"
    r"unlock|lock\s+(?:the\s+)?(?:door|house)|open\s+(?:the\s+)?(?:door|garage)|"
    r"(?:open|close|shut)\s+(?:the\s+)?(?:door|garage|gate|blinds|curtains)|"
    r"(?:dim|brighten)\s+(?:the\s+)?(?:light|lights|lamp|lamps)|"
    r"(?:raise|lower|increase|decrease|adjust)\s+(?:the\s+)?(?:temperature|thermostat|heating)|"
    r"(?:play|pause|resume)\s+(?:the\s+)?(?:music|playlist|radio)|"
    r"arm|disarm|start\s+(?:the\s+)?(?:routine|car|music|charging)|"
    r"stop\s+(?:the\s+)?(?:routine|car|music|charging)|"
    r"activate|deactivate|charge\s+(?:the\s+)?car|"
    r"delete|remove|erase|reset|purchase|buy|transfer)\b"
)
_STRUCTURED_SECRET = re.compile(
    r"(?i)(?:\bsk-[A-Za-z0-9_-]{12,}\b|"
    r"\b(?:eyJ[A-Za-z0-9_-]{20,}\.)[A-Za-z0-9_.-]+|"
    r"\b[A-Fa-f0-9]{32,}\b|"
    r"\b\d(?:[ -]?\d){11,18}\b)"
)


def safe_chat_text(value):
    """Return harmless short text, or None if it should not be remembered."""
    if type(value) is not str or not value.strip():
        return None
    if any(ord(char) < 32 and char not in "\t" for char in value):
        return None
    if _SENSITIVE.search(value) or _ACTION.search(value) or _STRUCTURED_SECRET.search(value):
        return None
    return value[:160]
