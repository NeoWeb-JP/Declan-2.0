"""Read-only result lookup for the exact script context returned by HA REST."""
import asyncio
import re

from aiohttp import web
from homeassistant.components.http import HomeAssistantView

from .ha_audit import build_report, trace_steps


async def lookup_result(hass, entity_id, context_id):
    from homeassistant.components.trace.util import async_get_trace, async_list_traces

    unknown = {"entity_id": entity_id, "context_id": context_id, "status": "unverified"}
    component = hass.data.get("script")
    entity = component.get_entity(entity_id) if component else None
    item_id = getattr(entity, "unique_id", None)
    if not isinstance(item_id, str):
        return unknown
    key = "script." + item_id
    matched = []
    async with asyncio.timeout(3):
        rows = await async_list_traces(hass, "script", key)
        rows = sorted(rows, key=lambda row: str((row.get("timestamp") or {}).get("start") or ""), reverse=True)[:20]
        for row in rows:
            try:
                detail = await async_get_trace(hass, key, row["run_id"])
            except KeyError:
                continue
            context = detail.get("context")
            found_id = context.get("id") if isinstance(context, dict) else getattr(context, "id", None)
            if found_id == context_id:
                matched.append({**row, "audit_steps": trace_steps(detail)})
    if len(matched) != 1:
        return unknown
    # Share the audit's conservative outcome classification; no device claims.
    report = build_report({}, {}, set(), set(), set(),
                          [{"entity_id": entity_id, "config": {}}], {entity_id: matched})
    execution = report["routines"][0]["executions"][0]
    return {**unknown, "status": execution["status"], "run_id": execution["run_id"],
            "evidence": "ha_trace", "steps": execution["steps"]}


class DeclanScriptResultView(HomeAssistantView):
    url = "/api/declan_two/script-result"
    name = "api:declan_two:script_result"
    requires_auth = True

    async def get(self, request):
        user = request.get("hass_user")
        if user is None or not user.is_admin:
            raise web.HTTPForbidden()
        entity_id = request.query.get("entity_id", "")
        context_id = request.query.get("context_id", "")
        if not re.fullmatch(r"script\.[a-z0-9_]+", entity_id) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", context_id):
            raise web.HTTPBadRequest()
        try:
            result = await lookup_result(request.app["hass"], entity_id, context_id)
        except Exception:
            result = {"entity_id": entity_id, "context_id": context_id, "status": "unverified"}
        return web.json_response(result, headers={"Cache-Control": "no-store"})
