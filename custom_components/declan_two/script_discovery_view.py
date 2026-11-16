"""Read-only, conservative HA script inspection for automatic voice execution.

Only direct light services with explicit light entities are auto-approved.
All templates, nested scripts, conditions, other domains and unknown sources fail closed.
"""
import json
import re
from pathlib import Path

from aiohttp import web
from homeassistant.components.http import HomeAssistantView

ENTITY = re.compile(r"script\.[a-z0-9_]+\Z")
LIGHT = re.compile(r"light\.[a-z0-9_]+\Z")
SAFE_ACTIONS = {"light.turn_on", "light.turn_off", "light.toggle"}


def inspect_script(definition):
    if not isinstance(definition, dict) or not isinstance(definition.get("sequence"), list):
        return False
    sequence = definition["sequence"]
    if not 1 <= len(sequence) <= 50 or definition.get("fields"):
        return False
    for step in sequence:
        if not isinstance(step, dict) or set(step) - {"alias", "action", "service", "target", "data", "enabled"}:
            return False
        if step.get("enabled") is False:
            continue
        service = step.get("action", step.get("service"))
        if service not in SAFE_ACTIONS:
            return False
        target = step.get("target")
        if not isinstance(target, dict) or set(target) != {"entity_id"}:
            return False
        entities = target["entity_id"]
        if isinstance(entities, str):
            entities = [entities]
        if not isinstance(entities, list) or not 1 <= len(entities) <= 30 or not all(
            isinstance(item, str) and LIGHT.fullmatch(item) for item in entities
        ):
            return False
        data = step.get("data", {})
        if not isinstance(data, dict) or set(data) - {"brightness_pct", "brightness", "transition"}:
            return False
        if any(type(v) not in (int, float) or v < 0 or v > (255 if k == "brightness" else 100)
               for k, v in data.items()):
            return False
    return True


def read_definitions(hass):
    """Use HA's own YAML loader and UI script storage. Missing sources fail closed."""
    result = {}
    path = Path(hass.config.path("scripts.yaml"))
    if path.is_file():
        from homeassistant.util.yaml import load_yaml
        definitions = load_yaml(str(path))
        if isinstance(definitions, dict):
            result.update(definitions)
    storage = Path(hass.config.path(".storage/script"))
    if storage.is_file():
        raw = json.loads(storage.read_text(encoding="utf-8"))
        data = raw.get("data", {})
        items = data.get("items", []) if isinstance(data, dict) else []
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and isinstance(item.get("id"), str):
                    result[item["id"]] = item
    return result


class DeclanScriptDiscoveryView(HomeAssistantView):
    url = "/api/declan_two/script-discovery"
    name = "api:declan_two:script_discovery"
    requires_auth = True

    async def get(self, request):
        user = request.get("hass_user")
        if user is None or not user.is_admin:
            raise web.HTTPForbidden()
        hass = request.app["hass"]
        from homeassistant.helpers import area_registry, entity_registry
        areas = area_registry.async_get(hass)
        entities = entity_registry.async_get(hass)
        scripts = []
        for entity in hass.states.async_all("script"):
            if not ENTITY.fullmatch(entity.entity_id):
                continue
            key = entity.entity_id[7:]
            # An entity in the state machine is not proof that its script
            # action exists. Only expose services registered by Home Assistant.
            # Stale/restored entities must never be offered for execution.
            if not hass.services.has_service("script", key):
                continue
            entry = entities.async_get(entity.entity_id)
            area_id = entry.area_id if entry else None
            if not area_id and entry and entry.device_id:
                from homeassistant.helpers import device_registry
                device = device_registry.async_get(hass).async_get(entry.device_id)
                area_id = device.area_id if device else None
            area = areas.async_get_area(area_id) if area_id else None
            scripts.append({
                "entity_id": entity.entity_id,
                "name": entity.attributes.get("friendly_name") or key.replace("_", " ").title(),
                "area": area.name if area else "",
                "fields": sorted((entity.attributes.get("fields") or {}).keys())
                          if isinstance(entity.attributes.get("fields"), dict) else [],
                "safe": True,
                "reason": "available_in_home_assistant",
            })
        return web.json_response({"scripts": scripts, "inspection": "complete"},
                                 headers={"Cache-Control": "no-store"})
