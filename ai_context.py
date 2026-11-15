"""Bound AI context without silently granting access to other devices."""
import re

IGNORE = frozenset({
    "a", "all", "and", "at", "can", "could", "do", "for", "in", "is",
    "light", "lights", "on", "off", "open", "close", "cover", "covers",
    "fan", "fans", "switch", "switches", "please", "set", "the", "to",
    "turn", "you", "would", "my", "me", "it", "up", "down",
})


def select(inventory, utterance, *, limit=100):
    if not isinstance(inventory, list) or not isinstance(utterance, str):
        raise ValueError("Invalid AI context")
    if len(inventory) <= limit:
        return inventory
    words = set(re.findall(r"[a-z0-9]+", utterance.casefold())) - IGNORE
    if not words:
        raise ValueError("Please specify a room or device")
    selected = []
    for row in inventory:
        attrs = row.get("attributes", {})
        haystack = " ".join((row.get("entity_id", ""),
                             str(attrs.get("friendly_name", "")),
                             str(row.get("declan_area", "")))).casefold()
        if any(re.search(r"(?<![a-z0-9])" + re.escape(word) + r"(?![a-z0-9])", haystack)
               for word in words):
            selected.append(row)
    if not selected or len(selected) > limit:
        raise ValueError("Please specify a more precise room or device")
    return selected
