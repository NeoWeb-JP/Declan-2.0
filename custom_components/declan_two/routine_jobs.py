"""Accepted HA routine jobs: immediate receipt, durable result, no automatic replay."""
import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import re

from aiohttp import web
from homeassistant.components.http import HomeAssistantView

from .script_discovery_view import declared_script_fields
from .routine_job_results import RoutineJobOutcome, StoredRoutineJob, job_outcome

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class RoutineJobSummary:
    outcome: RoutineJobOutcome
    steps: tuple[dict, ...] = ()
    reason: str | None = None

    def __post_init__(self):
        if not isinstance(self.outcome, RoutineJobOutcome):
            raise TypeError("outcome must be a RoutineJobOutcome")

    def to_wire(self) -> dict:
        summary: dict[str, object] = {"outcome": self.outcome.value, "steps": [dict(step) for step in self.steps]}
        if self.reason is not None:
            summary["reason"] = self.reason
        return summary


ACTIVE = frozenset({RoutineJobOutcome.QUEUED, RoutineJobOutcome.RUNNING})


def timestamp():
    return datetime.now(timezone.utc).isoformat()


async def job_state(hass):
    from homeassistant.helpers.storage import Store
    key = "declan_two_routine_jobs"
    if key not in hass.data:
        hass.data[key] = {"store": Store(hass, 1, key), "lock": asyncio.Lock(), "jobs": None}
    state = hass.data[key]
    async with state["lock"]:
        if state["jobs"] is None:
            saved = await state["store"].async_load()
            state["jobs"] = saved.get("jobs", {}) if isinstance(saved, dict) and isinstance(saved.get("jobs"), dict) else {}
            # A restart cannot establish whether old side effects completed.
            # Preserve the evidence and never replay an interrupted request.
            recovered = False
            for job in state["jobs"].values():
                if job_outcome(job.get("outcome")) in ACTIVE:
                    job.update(outcome=RoutineJobOutcome.UNVERIFIED.value, reason="interrupted", updated_at=timestamp())
                    recovered = True
            if recovered:
                await state["store"].async_save({"jobs": state["jobs"]})
    return state


async def save_job(state, job):
    async with state["lock"]:
        jobs = dict(state["jobs"])
        jobs[job["job_id"]] = dict(job)
        completed = sorted((key for key, value in jobs.items() if job_outcome(value["outcome"]) not in ACTIVE),
                           key=lambda key: jobs[key]["updated_at"])
        while len(jobs) > 100 and completed:
            jobs.pop(completed.pop(0))
        await state["store"].async_save({"jobs": jobs})
        state["jobs"] = jobs


def summarize_result_typed(result, job, fields) -> RoutineJobSummary | None:
    """Retain bounded result evidence, never script inputs or raw error text."""
    if not isinstance(result, Mapping) or "outcome" not in result:
        return None
    if (("request_id" in fields and result.get("request_id") != job["job_id"])
            or ("routine_id" in fields and result.get("routine_id") != job["entity_id"])):
        return RoutineJobSummary(RoutineJobOutcome.UNVERIFIED, reason="result_correlation_failed")
    value = result["outcome"]
    outcome = {"success": RoutineJobOutcome.REPORTED_SUCCESS, "partial": RoutineJobOutcome.PARTIAL,
               "failed": RoutineJobOutcome.FAILED, "cancelled": RoutineJobOutcome.CANCELLED,
               "busy": RoutineJobOutcome.BUSY}.get(value, RoutineJobOutcome.UNVERIFIED) if isinstance(value, str) else RoutineJobOutcome.UNVERIFIED
    raw = result.get("steps", [])
    if not isinstance(raw, list) or len(raw) > 200:
        return RoutineJobSummary(RoutineJobOutcome.UNVERIFIED, reason="invalid_steps")
    if outcome is RoutineJobOutcome.REPORTED_SUCCESS and any(not isinstance(step, Mapping) or
            (step.get("required", True) and step.get("status") not in ("confirmed", "already_set")) for step in raw):
        outcome = RoutineJobOutcome.UNVERIFIED
    steps = [{**{key: step[key][:240] for key in ("target", "action", "entity_id", "status") if isinstance(step.get(key), str)},
              "required": step.get("required", True) is not False} for step in raw if isinstance(step, Mapping)]
    reason = result.get("reason_code")
    safe_reason = reason if isinstance(reason, str) and re.fullmatch(r"[a-z0-9_]{1,80}", reason) else None
    return RoutineJobSummary(outcome, tuple(steps), safe_reason)


def summarize_result(result, job, fields):
    summary = summarize_result_typed(result, job, fields)
    return summary.to_wire() if summary is not None else None


async def run_job(hass, state, job, service, parameters, fields, context):
    final = {**job, "outcome": RoutineJobOutcome.RUNNING.value, "updated_at": timestamp()}
    try:
        await save_job(state, final)
        result = await hass.services.async_call("script", service, parameters,
                                                blocking=True, return_response=True, context=context)
        typed_summary = summarize_result_typed(result, job, fields)
        if typed_summary is None:
            from .script_result_view import lookup_result_typed
            evidence = await lookup_result_typed(hass, job["entity_id"], context.id)
            summary = evidence.to_job_wire()
        else:
            summary = typed_summary.to_wire()
        final.update(summary)
    except asyncio.CancelledError:
        final.update(outcome=RoutineJobOutcome.UNVERIFIED.value, reason="interrupted")
        raise
    except Exception as error:
        final.update(outcome=RoutineJobOutcome.FAILED.value, reason=type(error).__name__)
    finally:
        final["updated_at"] = timestamp()
        try:
            await asyncio.shield(save_job(state, final))
        except Exception:
            _LOGGER.warning("Declan background result could not be saved for %s", job["job_id"])
        log = _LOGGER.warning if job_outcome(final["outcome"]) not in {RoutineJobOutcome.REPORTED_SUCCESS, RoutineJobOutcome.FINISHED_UNVERIFIED} else _LOGGER.info
        log("Declan background routine %s job %s: %s", job["entity_id"], job["job_id"], final["outcome"])


async def latest_results_typed(hass) -> dict[str, StoredRoutineJob]:
    state = await job_state(hass)
    latest = {}
    for job in state["jobs"].values():
        entity_id = job["entity_id"]
        if entity_id not in latest or job["created_at"] > latest[entity_id]["created_at"]:
            latest[entity_id] = dict(job)
    return {entity_id: StoredRoutineJob(job) for entity_id, job in latest.items()}


async def latest_results(hass):
    return {entity_id: job.to_wire() for entity_id, job in (await latest_results_typed(hass)).items()}


class DeclanRoutineJobsView(HomeAssistantView):
    url = "/api/declan_two/routine-jobs"
    name = "api:declan_two:routine_jobs"
    requires_auth = True

    async def post(self, request):
        user = request.get("hass_user")
        if user is None or not user.is_admin:
            raise web.HTTPForbidden()
        if request.content_length is None or not 0 < request.content_length <= 8192:
            raise web.HTTPBadRequest()
        try:
            body = await request.json()
        except (ValueError, TypeError):
            raise web.HTTPBadRequest() from None
        if (not isinstance(body, dict) or not isinstance(body.get("entity_id"), str)
                or not re.fullmatch(r"script\.[a-z0-9_]+", body["entity_id"])
                or not isinstance(body.get("job_id"), str) or not re.fullmatch(r"declan-[a-f0-9]{32}", body["job_id"])
                or not isinstance(body.get("parameters"), dict)):
            raise web.HTTPBadRequest()
        hass = request.app["hass"]
        component = hass.data.get("script")
        entity = component.get_entity(body["entity_id"]) if component else None
        service = getattr(entity, "unique_id", None)
        if not isinstance(service, str) or not hass.services.has_service("script", service):
            return web.json_response({"error": "script_unavailable"}, status=404)
        fields = declared_script_fields(entity)
        parameters = {key: value for key, value in body["parameters"].items() if key in fields
                      and type(value) in (str, int, float, bool) and (not isinstance(value, str) or len(value) <= 1000)}
        if "request_id" in fields:
            parameters["request_id"] = body["job_id"]
        if "routine_id" in fields:
            parameters["routine_id"] = body["entity_id"]
        context = self.context(request)
        try:
            state = await job_state(hass)
        except Exception:
            return web.json_response({"error": "storage_unavailable"}, status=503)
        async with state["lock"]:
            if body["job_id"] in state["jobs"]:
                if state["jobs"][body["job_id"]]["entity_id"] != body["entity_id"]:
                    raise web.HTTPBadRequest()
                return web.json_response({"status": "accepted", "job_id": body["job_id"], "entity_id": body["entity_id"]}, status=202)
            if any(row["entity_id"] == body["entity_id"] and job_outcome(row["outcome"]) in ACTIVE for row in state["jobs"].values()):
                return web.json_response({"error": "already_running"}, status=409)
            if sum(job_outcome(row["outcome"]) in ACTIVE for row in state["jobs"].values()) >= 4:
                return web.json_response({"error": "queue_full"}, status=429)
            job = {"job_id": body["job_id"], "entity_id": body["entity_id"], "outcome": RoutineJobOutcome.QUEUED.value,
                   "created_at": timestamp(), "updated_at": timestamp(), "steps": []}
            jobs = {**state["jobs"], body["job_id"]: job}
            try:
                await state["store"].async_save({"jobs": jobs})
            except Exception:
                return web.json_response({"error": "storage_unavailable"}, status=503)
            state["jobs"] = jobs
        work = run_job(hass, state, job, service, parameters, fields, context)
        try:
            hass.async_create_background_task(work, "declan-routine-" + body["job_id"], eager_start=False)
        except Exception:
            work.close()
            await save_job(state, {**job, "outcome": RoutineJobOutcome.FAILED.value, "reason": "scheduling_failed", "updated_at": timestamp()})
            return web.json_response({"error": "scheduling_failed"}, status=503)
        return web.json_response({"status": "accepted", "job_id": body["job_id"], "entity_id": body["entity_id"]},
                                 status=202, headers={"Cache-Control": "no-store"})
