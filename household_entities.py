"""Validated Home Assistant entity configuration for household-specific helpers."""

import re

import configuration


def resolve(key, domain, legacy_default):
    """Use saved native settings or environment without trusting arbitrary paths."""
    value = configuration.get(key, legacy_default)
    if not isinstance(value, str) or not re.fullmatch(
        re.escape(domain) + r"\.[a-z0-9_]+", value
    ):
        raise ValueError("Invalid configured Home Assistant " + domain + " entity")
    return value


def guest_mode():
    return resolve("DECLAN_GUEST_MODE_ENTITY", "input_boolean", "input_boolean.guest_mode")


def guest_register():
    return resolve("DECLAN_GUEST_REGISTER_ENTITY", "input_text", "input_text.guests_in_charge")


def projector_power():
    return resolve("DECLAN_PROJECTOR_POWER_ENTITY", "switch", "switch.projector_power_socket")
