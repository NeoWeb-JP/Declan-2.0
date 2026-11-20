"""Read the actual Home Assistant Assist exposure policy for AI planning.

The native HA integration is the authority. Unavailable policy fails closed.
"""
import logging

_LOGGER = logging.getLogger(__name__)
# media_player is included so the conversation agent can switch TVs; the AI
# planner still filters by its own allowed domains.
DOMAINS = frozenset({"light", "switch", "fan", "cover", "media_player"})


def _should_expose_function():
    from homeassistant.components.homeassistant import exposed_entities
    # HA's public helper is async_should_expose(hass, assistant, entity_id).
    function = getattr(exposed_entities, "async_should_expose", None)
    if function is None:
        raise ImportError("Home Assistant exposure helper is unavailable")
    return function


def exposed_for_declan(hass):
    result = []
    try:
        should_expose = _should_expose_function()
        for state in hass.states.async_all():
            entity_id = state.entity_id
            if entity_id.split(".", 1)[0] not in DOMAINS:
                continue
            if should_expose(hass, "conversation", entity_id):
                result.append(entity_id)
        entities = sorted(set(result))
        return entities if len(entities) <= 1000 and sum(len(x) + 4 for x in entities) <= 40000 else []
    except (KeyError, AttributeError, RuntimeError, ImportError) as error:
        # Never send an unrestricted inventory when HA exposure is unavailable.
        _LOGGER.warning("Declan could not read the Assist exposure list (%s); AI device control is off",
                        type(error).__name__)
        return []
