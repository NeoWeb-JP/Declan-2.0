"""Verified Home Assistant routine execution and completion handling."""
import json
import re
import sqlite3
from urllib.error import HTTPError
from execution_results import ExecutionResult, Outcome, MovieLaunchStatus
from declan.ha.script_provider_results import ScriptProviderResult, ScriptReportedOutcome
from routine_action_evidence import RoutineActionStatus


def run_routine_result(period, *, action_results=None, movie_action=None, movie_room="lounge", movie_app=None, approved=False, gates, connect, registry, cooldown, token_hex, request_factory, tracker, completion, launch_app, evidence_factory, append_evidence, sleep_fn):
    """Call the configured Home Assistant routine once and read its result."""
    salutation = "Movie Time." if movie_action else f"Good {period}."
    lock = gates.for_routine(period, movie_action=movie_action, movie_room=movie_room)
    connection = connect()
    if connection is None:
        return ExecutionResult(f"{salutation} The Home Assistant connection isn't configured.", Outcome.NOT_CONFIGURED), None
    url, headers, opener = connection
    routine_key = ("movie_bedroom" if movie_room == "bedroom" else "movie") if movie_action else period
    try:
        mapped = registry.load().get(routine_key)
    except (OSError, ValueError, sqlite3.Error):
        return ExecutionResult(f"{salutation} Routine configuration is unavailable.", Outcome.NOT_CONFIGURED), None
    if not mapped:
        return ExecutionResult(f"{salutation} Map a Home Assistant script for {routine_key} in Declan Settings.", Outcome.NOT_CONFIGURED), None
    if mapped["sensitive"] and not approved:
        return ExecutionResult(f"{salutation} This routine needs explicit confirmation.", Outcome.UNRESOLVED), None
    script = mapped["script"]
    remote = mapped.get("remote", "").strip() if movie_app else ""
    if movie_app and not re.fullmatch(r"remote\.[a-z0-9_]+", remote):
        return ExecutionResult(f"I don't have a compatible app remote configured for the {movie_room}.", Outcome.NOT_CONFIGURED), None
    if not re.fullmatch(r"script\.[a-z0-9_]+", script):
        return ExecutionResult(f"{salutation} The routine script isn't configured.", Outcome.NOT_CONFIGURED), None
    if not lock.acquire(blocking=False):
        return ExecutionResult(f"The {period} routine request is already in progress.", Outcome.BUSY), None
    try:
        attempt_key = (period, movie_room, movie_action) if movie_action else period
        if not cooldown.claim(attempt_key):
            return ExecutionResult(f"I already sent a {period} request. I haven't sent another.", Outcome.DUPLICATE), None
        service = script.split(".", 1)[1]
        request_id = "declan-" + token_hex(16)
        parameters = {**mapped["fields"], "request_id": request_id, "routine_id": script}
        if movie_action:
            parameters["requested_action"] = movie_action
        request = request_factory(
            f"{url}/api/services/script/{service}?return_response",
            data=json.dumps(parameters).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with tracker(routine_key, script):
                with opener.open(request, timeout={"morning": 8, "night": 20, "movie": 55}[period]) as response:
                    payload = json.loads(response.read(65536))
        except HTTPError as error:
            code = error.code
            error.close()
            if code in {401, 403, 404}:
                return ExecutionResult(f"{salutation} Home Assistant couldn't accept the configured routine.", Outcome.REJECTED), None
            return ExecutionResult(f"{salutation} I couldn't confirm the routine completed. Check its Home Assistant trace.", Outcome.UNVERIFIED), None
        except (OSError, ValueError):
            return ExecutionResult(f"{salutation} I couldn't confirm the routine completed. Check its Home Assistant trace.", Outcome.UNVERIFIED), None
        result = payload.get("service_response") if isinstance(payload, dict) else None
        if movie_action and isinstance(result, dict) and set(result) == {script}:
            result = result[script]
        if movie_action or (isinstance(result, dict) and "schema_version" in result):
            execution, detail = completion(result, request_id, script, period, movie_action, action_results)
            outcome = execution.outcome
            if movie_app:
                if outcome is Outcome.REPORTED_SUCCESS:
                    sleep_fn(7)
                    launch = launch_app(connection, remote, movie_app)
                    status, note = launch.status, launch.detail
                else:
                    status, note = MovieLaunchStatus.SKIPPED, detail or "Movie Time was not verified."
                if action_results is not None:
                    evidence = evidence_factory(movie_app[0], status, remote,
                                                   f"{note} Remote: {remote}. Command: app:{movie_app[1]}.")
                    append_evidence(action_results, evidence)
            return execution, detail
        return ExecutionResult(f"{salutation} Home Assistant did not return a correlated completion result.", Outcome.UNVERIFIED), None
    finally:
        lock.release()


def routine_completion_result(result, request_id, routine_id, period, movie_action, action_results, *, parse_steps, extend_evidence, sass):
    salutation = "Movie Time." if movie_action else f"Good {period}."
    if (not isinstance(result, dict) or result.get("schema_version") != 1
            or result.get("request_id") != request_id or result.get("routine_id") != routine_id):
        if movie_action:
            detail = "Home Assistant didn't return a Movie Time result that matched this request."
            return ExecutionResult(f"{salutation} {detail}", Outcome.UNVERIFIED), detail
        return ExecutionResult(f"{salutation} I couldn't verify the result of this run.", Outcome.UNVERIFIED), None
    outcome = ScriptProviderResult.parse(result.get("outcome")).outcome
    resolved = result.get("resolved_action")
    if movie_action and outcome in (ScriptReportedOutcome.SUCCESS, ScriptReportedOutcome.PARTIAL):
        expected = ("start", "end") if movie_action == "toggle" else (movie_action,)
        if resolved not in expected:
            return ExecutionResult("Movie Time. I couldn't verify that the result matched the requested direction.", Outcome.UNVERIFIED), None
    raw_steps = result.get("steps")
    steps = parse_steps(raw_steps)
    if action_results is not None:
        extend_evidence(action_results, steps)
    required = [step for step in steps if step.required is not False]
    confirmed = any(step.completed for step in required)
    if outcome is ScriptReportedOutcome.SUCCESS and (not required or not isinstance(raw_steps, (list, dict)) or len(steps) != len(raw_steps)
                                 or any(not step.completed for step in required)):
        outcome = ScriptReportedOutcome.PARTIAL if confirmed else ScriptReportedOutcome.UNKNOWN
    elif outcome is ScriptReportedOutcome.PARTIAL and not confirmed:
        outcome = ScriptReportedOutcome.UNKNOWN
    elif outcome is ScriptReportedOutcome.FAILED and confirmed:
        outcome = ScriptReportedOutcome.PARTIAL
    if outcome is ScriptReportedOutcome.SUCCESS:
        guest_mode = result.get("guest_mode")
        if movie_action:
            salutation = "Starting Movie Time." if resolved == "start" else "Ending Movie Time."
        category = f"movie_{resolved}" if movie_action else f"good_{period}"
        reply = sass(salutation, category, guest_mode)
        bedtime = result.get("bedtime")
        if period == "night" and guest_mode == "off" and isinstance(bedtime, dict):
            battery = bedtime.get("battery_percent")
            temperature = bedtime.get("indoor_temperature")
            if type(battery) is int and 0 <= battery <= 50:
                reminder = sass(f"The Peugeot is at {battery}% and isn't plugged in.", "bedtime_ev", guest_mode)
                reply += f" {reminder}"
            if isinstance(temperature, (int, float)) and type(temperature) in (int, float) and -40 <= temperature <= 16:
                reply += f" It's {temperature:g} degrees indoors and the heating isn't running."
        detail = ("Home Assistant reports all lights are off." if period == "night"
                  else "Home Assistant confirmed the required steps.")
        return ExecutionResult(reply, Outcome.REPORTED_SUCCESS), detail
    if outcome is ScriptReportedOutcome.BUSY:
        return ExecutionResult(f"{salutation} The routine is already in progress.", Outcome.BUSY), None
    verified = [step.target.replace("_", " ") for step in required if step.completed]
    failed = [step.target.replace("_", " ") for step in required if step.status is RoutineActionStatus.FAILED]
    incomplete = [step.target.replace("_", " ") for step in required
                  if not step.completed and step.status is not RoutineActionStatus.FAILED]
    details = []
    if verified:
        details.append("Home Assistant confirmed " + ", ".join(verified[:8]) + ".")
    if failed:
        details.append("These steps failed: " + ", ".join(failed[:8]) + ".")
    if incomplete:
        details.append("I couldn't confirm " + ", ".join(incomplete[:8]) + ".")
    detail = " ".join(details) or ("Home Assistant reported a failure." if outcome is ScriptReportedOutcome.FAILED
                                   else "I couldn't confirm the routine completed.")
    reply = f"{salutation} {detail}"
    if movie_action and outcome is ScriptReportedOutcome.PARTIAL and resolved in ("start", "end"):
        intro = "Starting Movie Time." if resolved == "start" else "Ending Movie Time."
        reply = sass(intro, f"movie_{resolved}", result.get("guest_mode"))
    final_outcome = (ScriptProviderResult(outcome).execution_outcome
                     if outcome in (ScriptReportedOutcome.PARTIAL, ScriptReportedOutcome.FAILED) else Outcome.UNVERIFIED)
    return ExecutionResult(reply, final_outcome), detail


def run_custom_routine_result(name, action_results=None, *, approved=False, parameters=None, registry, connect, areas_reader, token_hex, request_factory, tracker, parse_steps, extend_evidence):
    """Run a legacy mapped HA script; no per-script approval required."""
    try:
        item = registry.load().get(name)
    except (ValueError, OSError, sqlite3.Error):
        return ExecutionResult("Routine configuration is unavailable.", Outcome.UNVERIFIED), None
    if not item:
        return ExecutionResult("That routine is not configured.", Outcome.NOT_CONFIGURED), None
    connection = connect()
    if connection is None:
        return ExecutionResult("Home Assistant is not connected.", Outcome.NOT_CONFIGURED), None
    url, headers, opener = connection
    if parameters and "room" in parameters:
        areas = areas_reader(connection)
        if parameters["room"] not in areas:
            return ExecutionResult("I could not match that room to a Home Assistant area.", Outcome.UNRESOLVED), None
    script = item["script"]
    # Preserve legacy script parameters for existing installations.
    request_id = "declan-" + token_hex(16)
    payload = {**item["fields"], **(parameters or {}), "request_id": request_id, "routine_id": script}
    request = request_factory(f"{url}/api/services/script/{script.split('.', 1)[1]}?return_response",
                      data=json.dumps(payload).encode(), headers=headers, method="POST")
    with tracker(name, script):
        try:
            with opener.open(request, timeout=55) as response:
                result = json.loads(response.read(65536))
        except HTTPError as error:
            code = error.code
            error.close()
            return ExecutionResult(f"Home Assistant rejected {name} (HTTP {code}).", Outcome.FAILED), None
        except (OSError, ValueError):
            return ExecutionResult(f"I couldn't verify {name}. Check its Home Assistant trace.", Outcome.UNVERIFIED), None
        value = result.get("service_response") if isinstance(result, dict) else None
        if isinstance(value, dict) and set(value) == {script}:
            value = value[script]
        if not isinstance(value, dict) or value.get("request_id") != request_id or value.get("routine_id") != script:
            return ExecutionResult(f"{name} was requested, but completion was not verified.", Outcome.UNVERIFIED), None
        provider_result = ScriptProviderResult.parse(value.get("outcome"))
        status = provider_result.outcome
        if status not in {ScriptReportedOutcome.STARTED, ScriptReportedOutcome.SUCCESS,
                          ScriptReportedOutcome.PARTIAL, ScriptReportedOutcome.FAILED, ScriptReportedOutcome.CANCELLED}:
            return ExecutionResult(f"{name} returned no verified completion outcome.", Outcome.UNVERIFIED), None
        steps = parse_steps(value.get("steps"))
        if action_results is not None:
            extend_evidence(action_results, steps)
        required = [step for step in steps if step.required is not False]
        if status is ScriptReportedOutcome.SUCCESS and (not required or not isinstance(value.get("steps"), list) or len(steps) != len(value["steps"]) or any(not step.completed for step in required)):
            return ExecutionResult(f"{name} was started, but required steps were not verified.", Outcome.UNVERIFIED), None
        return ExecutionResult(f"{name} {status}.", provider_result.execution_outcome), None
