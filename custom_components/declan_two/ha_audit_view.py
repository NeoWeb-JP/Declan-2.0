"""Admin-only audit of current loaded HA sources, without service calls."""
import asyncio
import logging
from collections.abc import Mapping

from aiohttp import web
from homeassistant.components.http import HomeAssistantView

from .ha_audit import build_report, trace_steps

_LOGGER = logging.getLogger(__name__)


def registry_ids(entries):
    """Support older ID mappings and HA's current iterable entry collections."""
    if isinstance(entries, Mapping):
        return set(entries)
    return {entry if isinstance(entry, str) else entry.id for entry in entries}


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
                    traces.setdefault(entity_id, []).append(dict(row))
        except Exception:
            # HA internal interfaces vary. Never replace missing evidence with a pass.
            gaps.append(f"{domain}: retained traces unavailable")
    # Inspect only the five newest retained runs per routine. This catches
    # continue_on_error failures hidden by a normally finished trace summary.
    try:
        from homeassistant.components.trace.util import async_get_trace
        async with asyncio.timeout(10):
            for entity_id, rows in traces.items():
                rows.sort(key=lambda row: str((row.get("timestamp") or {}).get("start") or ""), reverse=True)
                del rows[5:]
                for row in rows:
                    key = f"{entity_id.split('.', 1)[0]}.{row['item_id']}"
                    try:
                        detail = await async_get_trace(hass, key, row["run_id"])
                        row["audit_steps"] = trace_steps(detail)
                    except (KeyError, TypeError, AttributeError):
                        gaps.append(f"{entity_id}: action trace details unavailable")
    except Exception:
        gaps.append("Action trace details unavailable; run summaries only")
    return build_report(states, registered, registry_ids(devices.devices),
                        {area.id for area in areas.async_list_areas()},
                        services, routines, traces, gaps)


class DeclanHAAuditView(HomeAssistantView):
    url = "/api/declan_two/ha-audit"
    name = "api:declan_two:ha_audit"
    requires_auth = True

    async def get(self, request):
        user = request.get("hass_user")
        if user is None or not user.is_admin:
            raise web.HTTPForbidden()
        try:
            report = await collect_report(request.app["hass"])
        except Exception as error:
            # Do not return exception messages or configs, which may contain secrets.
            _LOGGER.error("Home Assistant audit collection failed (%s)", type(error).__name__)
            return web.json_response({"error": "audit_collection_failed"}, status=503,
                                     headers={"Cache-Control": "no-store"})
        return web.json_response(report, headers={"Cache-Control": "no-store"})
