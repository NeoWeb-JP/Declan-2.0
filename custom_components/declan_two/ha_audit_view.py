"""Admin-only audit of current loaded HA sources, without service calls."""
import asyncio
from collections.abc import Mapping

from aiohttp import web
from homeassistant.components.http import HomeAssistantView

from .ha_audit import build_report


async def collect_report(hass):
    from homeassistant.helpers import area_registry, device_registry, entity_registry

    registry = entity_registry.async_get(hass)
    devices = device_registry.async_get(hass)
    areas = area_registry.async_get(hass)
    states = {state.entity_id: {"state": state.state,
                               "name": state.attributes.get("friendly_name", state.entity_id)}
              for state in hass.states.async_all()}
    registered = {key: {"disabled": bool(entry.disabled_by)}
                  for key, entry in registry.entities.items()}
    services = {f"{domain}.{service}" for domain, entries in hass.services.async_services().items()
                for service in entries}
    routines = []
    gaps = []
    traces = {}
    for domain in ("script", "automation"):
        component = hass.data.get(domain)
        loaded = {entity.entity_id: entity for entity in getattr(component, "entities", ())}
        ids = set(loaded) | {key for key in set(states) | set(registered) if key.startswith(domain + ".")}
        trace_ids = {}
        for entity_id in sorted(ids):
            entity = loaded.get(entity_id)
            raw = getattr(entity, "raw_config", None)
            config = dict(raw) if isinstance(raw, Mapping) else None
            # Expanded sequence covers blueprint actions without reading household files.
            script = getattr(entity, "script" if domain == "script" else "action_script", None)
            sequence = getattr(script, "sequence", None)
            if isinstance(sequence, (list, tuple)):
                config = {**(config or {}), "loaded_sequence": sequence}
            refs = {}
            for kind, attribute in (("entity", "referenced_entities"), ("device", "referenced_devices"), ("area", "referenced_areas")):
                try:
                    refs[kind] = list(getattr(entity, attribute, ()) or ())
                except Exception:
                    gaps.append(f"{entity_id}: {kind} references unavailable")
            state = states.get(entity_id, {})
            routines.append({"entity_id": entity_id, "name": state.get("name"),
                             "state": state.get("state"),
                             "disabled": registered.get(entity_id, {}).get("disabled", False),
                             "config": config, "references": refs})
            item_id = (raw or {}).get("id") if domain == "automation" else entity_id.split(".", 1)[1]
            if item_id is not None:
                trace_ids[str(item_id)] = entity_id
        try:
            from homeassistant.components.trace.util import async_list_traces
            async with asyncio.timeout(10):
                rows = await async_list_traces(hass, domain, None)
            for row in rows:
                entity_id = trace_ids.get(str(row.get("item_id")))
                if entity_id:
                    traces.setdefault(entity_id, []).append(row)
        except Exception:
            # HA internal interfaces vary. Never replace missing evidence with a pass.
            gaps.append(f"{domain}: retained traces unavailable")
    return build_report(states, registered, set(devices.devices), set(areas.areas),
                        services, routines, traces, gaps)


class DeclanHAAuditView(HomeAssistantView):
    url = "/api/declan_two/ha-audit"
    name = "api:declan_two:ha_audit"
    requires_auth = True

    async def get(self, request):
        user = request.get("hass_user")
        if user is None or not user.is_admin:
            raise web.HTTPForbidden()
        report = await collect_report(request.app["hass"])
        return web.json_response(report, headers={"Cache-Control": "no-store"})
