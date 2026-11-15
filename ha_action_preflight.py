"""HA action capability and safety preflight, without side effects."""
from action_plan import CandidateAction

# Services that cannot be safely inferred from the generic HA entity domain.
# Additional sensitive actions require explicit confirmation in the caller.
SENSITIVE_DOMAINS = frozenset({"script"})
UNAVAILABLE = frozenset({"unavailable", "unknown"})


def preflight(plan, inventory, *, confirmed_sensitive=False):
    """Fail the whole plan closed if any action is not safely actionable.

    inventory must come from the trusted HA inventory reader, never model text.
    Returns immutable candidates; caller must still check live HA permissions
    and verify post-dispatch state before reporting completion.
    """
    if not isinstance(plan, tuple) or not all(isinstance(x, CandidateAction) for x in plan):
        raise ValueError("Invalid plan")
    if not isinstance(inventory, list):
        raise ValueError("Invalid inventory")
    lookup = {}
    for row in inventory:
        if not isinstance(row, dict) or not isinstance(row.get("entity_id"), str):
            raise ValueError("Invalid inventory row")
        if row["entity_id"] in lookup:
            raise ValueError("Duplicate entity in inventory")
        lookup[row["entity_id"]] = row
    for action in plan:
        row = lookup.get(action.entity_id)
        if row is None or row.get("state") in UNAVAILABLE or not isinstance(row.get("state"), str):
            raise ValueError("Entity not currently available")
        if action.entity_id.split(".", 1)[0] in SENSITIVE_DOMAINS and not confirmed_sensitive:
            raise ValueError("Sensitive routine requires confirmation")
        attributes = row.get("attributes")
        if not isinstance(attributes, dict):
            raise ValueError("Missing capability attributes")
        if (action.entity_id.startswith("cover.")
                and attributes.get("device_class") in {"garage", "gate"}
                and not confirmed_sensitive):
            raise ValueError("Garage and gate controls require explicit confirmation")
        if action.service == "toggle":
            raise ValueError("Toggle is not safe without an explicit target state")
        if action.service in {"media_play", "media_pause", "media_stop"}:
            features = attributes.get("supported_features")
            if type(features) is not int:
                raise ValueError("Media capabilities not available")
            bit = {"media_pause": 1, "media_play": 16384, "media_stop": 4096}[action.service]
            if not features & bit:
                raise ValueError("Media service not supported")
    return plan
