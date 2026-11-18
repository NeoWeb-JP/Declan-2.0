"""Safe Guest Mode entity selection for Home Assistant TTS fallback lines."""

import re

DEFAULT_GUEST_MODE_ENTITY = "input_boolean.guest_mode"
_ENTITY = re.compile(r"input_boolean\.[a-z0-9_]+\Z")


def guest_mode_entity(value):
    """Fail closed on malformed or unrelated HA entity references."""
    if not isinstance(value, str) or not _ENTITY.fullmatch(value):
        raise ValueError("Select a valid input_boolean entity for Guest Mode.")
    return value


def guest_safe(hass, value=DEFAULT_GUEST_MODE_ENTITY):
    """Unknown or unavailable Guest Mode must never use private Home sass."""
    try:
        entity_id = guest_mode_entity(value)
    except ValueError:
        return True
    states = getattr(hass, "states", None)
    state = states.get(entity_id) if states is not None else None
    return state is None or getattr(state, "state", None) != "off"
