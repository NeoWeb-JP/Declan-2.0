"""Safely substitute configured household display names in built-in spoken lines."""

import re
import sqlite3

from declan.core import configuration

SETTINGS = {
    "{resident_one}": ("DECLAN_RESIDENT_ONE_NAME", "the cook"),
    "{resident_two}": ("DECLAN_RESIDENT_TWO_NAME", "your partner"),
    "{pet_dog}": ("DECLAN_DOG_NAME", "the dog"),
    "{pet_cat}": ("DECLAN_CAT_NAME", "the cat"),
}
NAME = re.compile(r"[A-Za-z][A-Za-z '-]{0,47}\Z")


def render(line):
    """Read names only for the current line, falling back to impersonal text."""
    if not isinstance(line, str) or not any(token in line for token in SETTINGS):
        return line
    for token, (key, fallback) in SETTINGS.items():
        if token not in line:
            continue
        try:
            supplied = configuration.get(key, "")
        except (OSError, sqlite3.Error):
            supplied = ""
        value = supplied.strip() if isinstance(supplied, str) else ""
        line = line.replace(token, value if NAME.fullmatch(value) else fallback)
    return line
