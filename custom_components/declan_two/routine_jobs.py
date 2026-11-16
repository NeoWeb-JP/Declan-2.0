"""Accepted HA routine jobs: immediate receipt, durable result, no automatic replay."""
import asyncio
from collections.abc import Mapping
from datetime import datetime, timezone
import logging
import re

from aiohttp import web
from homeassistant.components.http import HomeAssistantView

from .script_discovery_view import declared_script_fields

_LOGGER = logging.getLogger(__name__)
ACTIVE = {"queued", "running"}


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
                if job.get("outcome") in ACTIVE:
                    job.update(outcome="unverified", reason="interrupted", updated_at=timestamp())
                    recovered = True
            if recovered:
                await state["store"].async_save({"jobs": state["jobs"]})
    return state


async def save_job(state, job):
    async with state["lock"]:
        jobs = dict(state["jobs"])
        jobs[job["job_id"]] = dict(job)
        completed = sorted((key for key, value in jobs.items() if value["outcome"] not in ACTIVE),
                           key=lambda key: jobs[key]["updated_at"])
        while len(jobs) > 100 and completed:
            jobs.pop(completed.pop(0))
        await state["store"].async_save({"jobs": jobs})
        state["jobs"] = jobs


def summarize_result(result, job, fields):
    """Retain bounded result evidence, never script inputs or raw error text."""
    if not isinstance(result, Mapping) or "outcome" not in result:
        return None
    if (("request_id" in fields and result.get("request_id") != job["job_id"])
            or ("routine_id" in fields and result.get("routine_id") != job["entity_id"])):
        return {"outcome": "unverified", "reason": "result_correlation_failed", "steps": []}
    value = result["outcome"]
    outcome = {"success": "reported_success", "partial": "partial", "failed": "failed",
               "cancelled": "cancelled", "busy": "busy", "unknown": "unverified", "started": "unverified"}.get(value, "unverified") if isinstance(value, str) else "unverified"
    raw = result.get("steps", [])
    if not isinstance(raw, list) or len(raw) > 200:
        return {"outcome": "unverified", "reason": "invalid_steps", "steps": []}
    if outcome == "reported_success" and any(not isinstance(step, Mapping) or
            (step.get("required", True) and step.get("status") not in ("confirmed", "already_set")) for step in raw):
        outcome = "unverified"
    steps = [{**{key: step[key][:240] for key in ("target", "action", "entity_id", "status") if isinstance(step.get(key), str)},
              "required": step.get("required", True) is not False} for step in raw if isinstance(step, Mapping)]
    summary = {"outcome": outcome, "steps": steps}
    reason = result.get("reason_code")
    if isinstance(reason, str) and re.fullmatch(r"[a-z0-9_]{1,80}", reason):
        summary["reason"] = reason
    return summary


async def run_job(hass, state, job, service, parameters, fields, context):
    final = {**job, "outcome": "running", "updated_at": timestamp()}
    try:
        await save_job(state, final)
        result = await hass.services.async_call("script", service, parameters,
                                                blocking=True, return_response=True, context=context)
        summary = summarize_result(result, job, fields)
        if summary is None:
            from .script_result_view import lookup_result
            evidence = await lookup_result(hass, job["entity_id"], context.id)
            summary = {"outcome": evidence["status"], "steps": evidence.get("steps", []), "run_id": evidence.get("run_id")}
        final.update(summary)
    except asyncio.CancelledError:
        final.update(outcome="unverified", reason="interrupted")
        raise
    except Exception as error:
        final.update(outcome="failed", reason=type(error).__name__)
    finally:
        final["updated_at"] = timestamp()
        try:
            await asyncio.shield(save_job(state, final))
        except Exception:
            _LOGGER.warning("Declan background result could not be saved for %s", job["job_id"])
        log = _LOGGER.warning if final["outcome"] not in {"reported_success", "finished_unverified"} else _LOGGER.info
        log("Declan background routine %s job %s: %s", job["entity_id"], job["job_id"], final["outcome"])


async def latest_results(hass):
    state = await job_state(hass)
    latest = {}
    for job in state["jobs"].values():
        entity_id = job["entity_id"]
        if entity_id not in latest or job["created_at"] > latest[entity_id]["created_at"]:
            latest[entity_id] = dict(job)
    return latest


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
            if any(row["entity_id"] == body["entity_id"] and row["outcome"] in ACTIVE for row in state["jobs"].values()):
                return web.json_response({"error": "already_running"}, status=409)
            if sum(row["outcome"] in ACTIVE for row in state["jobs"].values()) >= 4:
                return web.json_response({"error": "queue_full"}, status=429)
            job = {"job_id": body["job_id"], "entity_id": body["entity_id"], "outcome": "queued",
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
            await save_job(state, {**job, "outcome": "failed", "reason": "scheduling_failed", "updated_at": timestamp()})
            return web.json_response({"error": "scheduling_failed"}, status=503)
        return web.json_response({"status": "accepted", "job_id": body["job_id"], "entity_id": body["entity_id"]},
                                 status=202, headers={"Cache-Control": "no-store"})
