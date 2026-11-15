"""Read the actual Home Assistant Assist exposure policy for AI planning.

The native HA integration is the authority. Unavailable policy fails closed.
"""
DOMAINS = frozenset({"light", "switch", "fan", "cover"})


def exposed_for_declan(hass):
    result = []
    try:
        from homeassistant.components.homeassistant.exposed_entities import async_get_should_expose
        for state in hass.states.async_all():
            entity_id = state.entity_id
            if entity_id.split(".", 1)[0] not in DOMAINS:
                continue
            if async_get_should_expose(hass, "conversation", entity_id):
                result.append(entity_id)
        entities = sorted(set(result))
        return entities if len(entities) <= 1000 and sum(len(x) + 4 for x in entities) <= 40000 else []
    except (KeyError, AttributeError, RuntimeError, ImportError):
        # Never send an unrestricted inventory when HA exposure is unavailable.
        return []
