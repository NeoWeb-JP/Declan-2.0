"""Read-only result lookup for the exact script context returned by HA REST."""
import asyncio
from dataclasses import dataclass
import re

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
import logging

from .ha_audit import TraceExecution, TraceOutcome, classify_trace_typed, trace_step_wire, trace_steps_typed

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScriptTraceResult:
    entity_id: str
    context_id: str
    execution: TraceExecution | None = None

    @property
    def status(self) -> TraceOutcome:
        return self.execution.status if self.execution is not None else TraceOutcome.UNVERIFIED

    def to_wire(self) -> dict:
        result: dict[str, object] = {"entity_id": self.entity_id, "context_id": self.context_id, "status": self.status.value}
        if self.execution is not None:
            result.update(run_id=self.execution.run_id, evidence="ha_trace",
                          steps=[trace_step_wire(step) for step in self.execution.steps])
        return result

    def to_job_wire(self) -> dict:
        return {"outcome": self.status.value,
                "steps": [trace_step_wire(step) for step in self.execution.steps] if self.execution is not None else [],
                "run_id": self.execution.run_id if self.execution is not None else None}


async def lookup_result_typed(hass, entity_id, context_id) -> ScriptTraceResult:
    from homeassistant.components.trace.util import async_get_trace, async_list_traces

    unknown = ScriptTraceResult(entity_id, context_id)
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
                matched.append({**row, "audit_steps": trace_steps_typed(detail)})
    if len(matched) != 1:
        return unknown
    return ScriptTraceResult(entity_id, context_id, classify_trace_typed(matched[0]))


async def lookup_result(hass, entity_id, context_id):
    return (await lookup_result_typed(hass, entity_id, context_id)).to_wire()


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
            result = await lookup_result_typed(request.app["hass"], entity_id, context_id)
        except Exception as error:
            _LOGGER.warning("Script trace lookup failed (%s)", type(error).__name__)
            result = ScriptTraceResult(entity_id, context_id)
        return web.json_response(result.to_wire(), headers={"Cache-Control": "no-store"})
