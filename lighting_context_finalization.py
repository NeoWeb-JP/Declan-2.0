"""Build bounded, scoped lighting context for successful voice follow-ups."""
import re
from lighting_action_evidence import confirmed_lighting_entities

_PREVIEW_PREFIX = re.compile(r"^(?:preview|dry[ -]run)\b")


def confirmed_lighting_context(phrase, outcome, scope, action_results):
    """Return unique confirmed light entities, or an empty context when unsafe."""
    if _PREVIEW_PREFIX.match(phrase):
        return ()
    if outcome != "confirmed" or scope is None or len(action_results) >= 200:
        return ()
    return confirmed_lighting_entities(action_results)
