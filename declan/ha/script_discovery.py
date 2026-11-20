"""Discover and run Home Assistant scripts without per-script approval."""
from declan.core.execution_results import ExecutionResult, Outcome
from declan.ha.script_action_evidence import parse_script_actions
from declan.ai.action_evidence_buffer import extend_action_evidence
from declan.ha.script_provider_results import ScriptProviderResult, ScriptReportedOutcome, TraceProviderOutcome, CorrelatedTraceResult
from declan.ha.script_provider_results import BackgroundReceiptResult, BackgroundReceiptStatus
from declan.ha.script_provider_results import ScriptReason
import json
import re
import secrets
from dataclasses import dataclass
from enum import StrEnum
from declan.ha.script_discovery_cache import ScriptDiscoveryCache
from urllib.error import HTTPError
from urllib.request import Request
from urllib.parse import urlencode

CACHE = ScriptDiscoveryCache()
CACHE_SECONDS = 30


class DiscoveryError(StrEnum):
    NOT_CONNECTED = "not_connected"
    INSPECTION_UNAVAILABLE = "inspection_unavailable"
    INVALID = "invalid"


@dataclass(frozen=True)
class DiscoveryResult:
    scripts: tuple[dict, ...] = ()
    error: DiscoveryError | None = None

    def __post_init__(self):
        if not isinstance(self.scripts, tuple) or any(not isinstance(row, dict) for row in self.scripts):
            raise TypeError("scripts must be a tuple of mappings")
        if self.error is not None and not isinstance(self.error, DiscoveryError):
            raise TypeError("error must be a DiscoveryError or None")


class ScriptMatchStatus(StrEnum):
    MATCHED = "matched"
    AMBIGUOUS = "ambiguous"
    NO_MATCH = "no_match"


@dataclass(frozen=True)
class ScriptMatchResult:
    status: ScriptMatchStatus
    candidates: tuple[dict, ...] = ()

    def __post_init__(self):
        if (not isinstance(self.status, ScriptMatchStatus) or not isinstance(self.candidates, tuple)
                or any(not isinstance(row, dict) for row in self.candidates)):
            raise TypeError("match requires an enum status and tuple of candidates")
        expected = len(self.candidates)
        if ((self.status is ScriptMatchStatus.MATCHED and expected != 1)
                or (self.status is ScriptMatchStatus.AMBIGUOUS and expected < 2)
                or (self.status is ScriptMatchStatus.NO_MATCH and expected != 0)):
            raise ValueError("match status does not agree with candidates")

    @property
    def selected(self) -> dict:
        if self.status is not ScriptMatchStatus.MATCHED:
            raise ValueError("only an unambiguous match has a selected script")
        return self.candidates[0]


def normalise(value):
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", value.casefold()).split())


def phrases(item):
    name = normalise(item["name"])
    entity = normalise(item["entity_id"].removeprefix("script.").replace("_", " "))
    result = {name, entity}
    # Home Assistant script labels commonly include the assistant name.
    # Spoken "good night" should match "Declan - Good Night" without
    # requiring a separate Declan-side alias or routine mapping.
    for prefix in ("declan ", "declan local ", "declan 2 "):
        if name.startswith(prefix):
            result.add(name[len(prefix):])
        if entity.startswith(prefix):
            result.add(entity[len(prefix):])
    # A Home Assistant script may have a descriptive implementation suffix,
    # e.g. "Declan - Good Morning - Shared Local Routine". Resolve the short
    # spoken name to the real registered script rather than an obsolete alias.
    for alias in tuple(result):
        for suffix in (" shared local routine", " local routine"):
            if alias.endswith(suffix):
                result.add(alias.removesuffix(suffix))
    # "Declan - Sexy Time Controller" should respond to "sexy time".
    for alias in tuple(result):
        if alias.endswith(" controller"):
            result.add(alias.removesuffix(" controller"))
        # HA appends numeric suffixes when a script entity is duplicated.
        # The full name remains authoritative; an ambiguous alias is never
        # selected automatically when more than one script shares it.
        numbered = re.fullmatch(r"(.+?) [0-9]+", alias)
        if numbered:
            result.add(numbered[1])
    if name.endswith(" status"):
        result.update({"what is the " + name, "what is the status of the " + name.removesuffix(" status"),
                       "give me the " + name})
    return result


def discover_result(connection, *, fresh=False) -> DiscoveryResult:
    if connection is None:
        return DiscoveryResult(error=DiscoveryError.NOT_CONNECTED)
    url, headers, opener = connection
    if opener is None or not hasattr(opener, "open"):
        return DiscoveryResult(error=DiscoveryError.INSPECTION_UNAVAILABLE)
    cache_key = CACHE.key(url, headers)
    if not fresh:
        cached = CACHE.get(cache_key, seconds=CACHE_SECONDS)
        if cached is not None:
            return cached
    generation = CACHE.begin(cache_key)
    try:
        with opener.open(Request(url + "/api/declan_two/script-discovery", headers=headers), timeout=5) as response:
            payload = json.loads(response.read(512 * 1024))
        if not isinstance(payload, dict) or payload.get("inspection") != "complete":
            return DiscoveryResult(error=DiscoveryError.INSPECTION_UNAVAILABLE)
        rows = payload.get("scripts")
        if not isinstance(rows, list) or len(rows) > 20000:
            return DiscoveryResult(error=DiscoveryError.INVALID)
        valid = []
        for item in rows:
            if (isinstance(item, dict) and isinstance(item.get("name"), str)
                    and 0 < len(item["name"]) <= 120 and
                    isinstance(item.get("entity_id"), str) and
                    re.fullmatch(r"script\.[a-z0-9_]+", item["entity_id"]) and
                    type(item.get("safe")) is bool):
                valid.append(item)
        if len(valid) != len(rows):
            return DiscoveryResult(error=DiscoveryError.INVALID)
        result = DiscoveryResult(tuple(valid))
        CACHE.publish(cache_key, generation, result)
        return result
    except (OSError, ValueError, TypeError, HTTPError):
        return DiscoveryResult(error=DiscoveryError.INSPECTION_UNAVAILABLE)


def match_result(phrase, scripts) -> ScriptMatchResult:
    phrase = normalise(phrase)
    phrase = re.sub(r"^(?:please |run |start |execute |activate )", "", phrase)
    matches = [item for item in scripts if phrase in phrases(item)]
    if not matches:
        return ScriptMatchResult(ScriptMatchStatus.NO_MATCH)
    # Prefer the one HA script explicitly designed to return Declan's
    # correlated completion result. Other similarly named scripts may be
    # legacy wrappers or duplicates. This is capability-based, not a
    # hardcoded script entity ID. Never guess when multiple candidates qualify.
    if len(matches) > 1:
        response_capable = [
            item for item in matches
            if isinstance(item.get("fields"), list)
            and {"request_id", "routine_id"}.issubset(item["fields"])
        ]
        if len(response_capable) == 1:
            return ScriptMatchResult(ScriptMatchStatus.MATCHED, (response_capable[0],))
        return ScriptMatchResult(ScriptMatchStatus.AMBIGUOUS, tuple(matches))
    item = matches[0]
    return ScriptMatchResult(ScriptMatchStatus.MATCHED, (item,))


def completion_from_trace_result(connection, current, result):
    """Read evidence for this invocation, never the latest unrelated script run."""
    changed = result.get("changed_states") if isinstance(result, dict) else result
    if not isinstance(changed, list):
        return None
    contexts = {row["context"]["id"] for row in changed
                if isinstance(row, dict) and row.get("entity_id") == current["entity_id"]
                and isinstance(row.get("context"), dict)
                and isinstance(row["context"].get("id"), str)}
    if len(contexts) != 1:
        return None
    context_id = contexts.pop()
    url, headers, opener = connection
    query = urlencode({"entity_id": current["entity_id"], "context_id": context_id})
    try:
        with opener.open(Request(url + "/api/declan_two/script-result?" + query, headers=headers), timeout=5) as response:
            evidence = json.loads(response.read(65536))
    except HTTPError as error:
        error.close()
        return None
    except (OSError, ValueError, TypeError):
        return None
    trace = CorrelatedTraceResult.parse(evidence, entity_id=current["entity_id"], context_id=context_id)
    if trace is None:
        return None
    status, detail = trace.status, trace.detail
    if status is TraceProviderOutcome.FINISHED_UNVERIFIED:
        return ExecutionResult("Routine finished.", Outcome.EXECUTION_COMPLETED), detail
    if status is TraceProviderOutcome.PARTIAL:
        return ExecutionResult("The routine finished with action errors. Check its Home Assistant trace.", Outcome.PARTIAL), detail
    if status is TraceProviderOutcome.FAILED:
        return ExecutionResult("The routine failed. Check its Home Assistant trace.", Outcome.FAILED), detail
    if status is TraceProviderOutcome.CANCELLED:
        return ExecutionResult("The routine was cancelled.", Outcome.CANCELLED), detail
    if status is TraceProviderOutcome.RUNNING:
        return ExecutionResult("The routine is still running.", Outcome.STARTED), detail
    return None


def enqueue_result(connection, entity_id, parameters):
    """Return a validated typed background dispatch and its receipt detail."""
    from declan.core.local_outcome_contracts import routine_execution_result
    return routine_execution_result(_enqueue_provider(connection, entity_id, parameters))


def execute_result(connection, item, *, parameters=None, expect_response=False, action_results=None):
    """Return a validated typed Home Assistant script result and status detail."""
    from declan.core.local_outcome_contracts import routine_execution_result
    return routine_execution_result(_execute_provider(
        connection, item, parameters=parameters, expect_response=expect_response,
        action_results=action_results,
    ))


def _enqueue_provider(connection, entity_id, parameters):
    """Wait only for HA's durable job receipt, never for routine completion."""
    if connection is None:
        return ExecutionResult("Home Assistant is not connected.", Outcome.NOT_CONFIGURED), None
    url, headers, opener = connection
    job_id = "declan-" + secrets.token_hex(16)
    request = Request(url + "/api/declan_two/routine-jobs", headers=headers, method="POST",
                      data=json.dumps({"entity_id": entity_id, "job_id": job_id, "parameters": parameters}).encode())
    try:
        with opener.open(request, timeout=2) as response:
            data = json.loads(response.read(8192))
            receipt = BackgroundReceiptResult.parse(response.status, data, job_id=job_id, entity_id=entity_id)
            if receipt.status is not BackgroundReceiptStatus.ACCEPTED:
                return ExecutionResult("Home Assistant did not acknowledge the routine request.", Outcome.UNVERIFIED), None
    except HTTPError as error:
        code = error.code
        error.close()
        if code == 409:
            return ExecutionResult("That routine is already in progress.", Outcome.BUSY), None
        if code == 404:
            return ExecutionResult("Check that the script is available and update the Declan HA integration, then restart Home Assistant. Nothing was queued.", Outcome.NOT_CONFIGURED), None
        return ExecutionResult("Home Assistant rejected the routine request.", Outcome.FAILED), None
    except (OSError, ValueError, TypeError):
        return ExecutionResult("I couldn't confirm the routine request. It may still start; check the audit before retrying.", Outcome.UNVERIFIED), None
    return ExecutionResult("Routine requested.", Outcome.STARTED), "Background job " + job_id


def _execute_provider(connection, item, *, parameters=None, expect_response=False, action_results=None):
    """Verify the live HA script and send only parameters it declares."""
    discovery = discover_result(connection, fresh=True)
    if discovery.error is not None:
        return ExecutionResult("I couldn't verify that script exists in Home Assistant. Nothing was run.", Outcome.UNVERIFIED), None
    current = next((row for row in discovery.scripts if row["entity_id"] == item["entity_id"]), None)
    if not current:
        return ExecutionResult("That script is no longer available in Home Assistant.", Outcome.UNRESOLVED), None
    url, headers, opener = connection
    allowed_fields = current.get("fields", [])
    if not isinstance(allowed_fields, list):
        allowed_fields = []
    supplied = {key: value for key, value in (parameters or {}).items()
                if key in allowed_fields and isinstance(value, (str, int, float, bool))}
    payload = {"entity_id": current["entity_id"]}
    if supplied:
        payload["variables"] = supplied

    # Execute the script service itself. script.turn_on only confirms scheduling.
    service = current["entity_id"].split(".", 1)[1]
    request_id = "declan-" + secrets.token_hex(16)
    if "request_id" in allowed_fields:
        supplied["request_id"] = request_id
    if "routine_id" in allowed_fields:
        supplied["routine_id"] = current["entity_id"]
    request = Request(url + "/api/services/script/" + service + "?return_response",
                      headers=headers, method="POST",
                      data=json.dumps(supplied).encode())
    try:
        with opener.open(request, timeout=55) as response:
            if response.status not in (200, 201):
                return ExecutionResult("Home Assistant did not confirm script execution.", Outcome.UNVERIFIED), None
            result = json.loads(response.read(65536))
    except HTTPError as error:
        code = error.code
        # Preserve HA's useful validation reason. Never log tokens or headers.
        try:
            body = error.read(4096).decode("utf-8", errors="replace")
        except (OSError, ValueError):
            body = ""
        finally:
            error.close()
        try:
            parsed = json.loads(body)
            reason = parsed.get("message", "") if isinstance(parsed, dict) else ""
        except ValueError:
            reason = body
        reason = re.sub(r"[\r\n\t]+", " ", str(reason)).strip()[:240]
        # Some HA versions reject return_response for a script service that
        # does not advertise response support. Retry ONLY when HA explicitly
        # states this, never for an arbitrary 400 (which could be bad data).
        unsupported_response = (
            code == 400 and "response" in reason.casefold()
            and any(term in reason.casefold() for term in
                    ("does not support", "doesn't support", "not supported", "unsupported"))
        )
        if unsupported_response:
            plain_request = Request(url + "/api/services/script/" + service,
                                    headers=headers, method="POST",
                                    data=json.dumps(supplied).encode())
            try:
                with opener.open(plain_request, timeout=55) as response:
                    if response.status not in (200, 201):
                        return ExecutionResult("Home Assistant did not confirm script dispatch.", Outcome.UNVERIFIED), None
                    plain_result = json.loads(response.read(65536))
            except HTTPError as retry_error:
                retry_code = retry_error.code
                retry_error.close()
                return ExecutionResult(f"Home Assistant rejected script execution (HTTP {retry_code}).", Outcome.FAILED), None
            except (OSError, ValueError, TypeError):
                return ExecutionResult("Home Assistant could not confirm script execution.", Outcome.UNVERIFIED), None
            if not expect_response and (observed := completion_from_trace_result(connection, current, plain_result)):
                return observed
            return ExecutionResult(current["name"] + " was sent to Home Assistant, but this script service "
                    "does not support returning a completion result. Check the script trace.", Outcome.UNVERIFIED), None
        return ExecutionResult(f"Home Assistant rejected the script (HTTP {code})"
                + (f": {reason}" if reason else "."), Outcome.FAILED), None
    except (OSError, ValueError, TypeError):
        return ExecutionResult("Home Assistant did not return a valid script result. Check its trace.", Outcome.UNVERIFIED), None
    data = result.get("service_response") if isinstance(result, dict) else None
    if isinstance(data, dict) and current["entity_id"] in data:
        data = data[current["entity_id"]]
    if not isinstance(data, dict):
        if not expect_response and (observed := completion_from_trace_result(connection, current, result)):
            return observed
        return ExecutionResult("Home Assistant returned no script result. Check response_variable and traces.", Outcome.UNVERIFIED), None
    if "outcome" in data:
        if "request_id" in allowed_fields and data.get("request_id") != request_id:
            return ExecutionResult("Script result did not match this request.", Outcome.UNVERIFIED), None
        if "routine_id" in allowed_fields and data.get("routine_id") != current["entity_id"]:
            return ExecutionResult("Script result did not match this routine.", Outcome.UNVERIFIED), None
        provider_result = ScriptProviderResult.parse(data["outcome"], normalize=True, reason=data.get("reason_code"))
        outcome = provider_result.outcome
        if outcome is None:
            return ExecutionResult("Home Assistant returned an unknown script outcome.", Outcome.UNVERIFIED), None
        reasons = {
            ScriptReason.SCREEN_MOVING: "The projector screen is still moving. Please wait before trying Movie Time again.",
            ScriptReason.SCREEN_POSITION_UNVERIFIED: "I couldn't determine a safe screen position and direction. Movie Time was not run.",
            ScriptReason.REQUESTED_ACTION_INVALID: "Movie Time did not receive a valid start, end or toggle action. Nothing was run.",
        }
        guard_reason = provider_result.guard_reason
        if guard_reason is not None:
            return ExecutionResult(reasons[guard_reason], provider_result.execution_outcome), None
        evidence = parse_script_actions(data.get("steps", []))
        if outcome is ScriptReportedOutcome.SUCCESS and not evidence.required_steps_completed:
            return ExecutionResult("Script success was not confirmed by its required steps.", Outcome.UNVERIFIED), None
        description = {ScriptReportedOutcome.SUCCESS: "completed successfully", ScriptReportedOutcome.PARTIAL: "partially completed",
                       ScriptReportedOutcome.FAILED: "failed", ScriptReportedOutcome.CANCELLED: "was cancelled",
                       ScriptReportedOutcome.UNKNOWN: "could not be verified", ScriptReportedOutcome.STARTED: "started but not completed",
                       ScriptReportedOutcome.BUSY: "is already in progress"}[outcome]
        if action_results is not None:
            extend_action_evidence(action_results, evidence.steps)
        return ExecutionResult(current["name"] + " " + description + ".", provider_result.execution_outcome), None
    for key in ("speech", "reply", "message", "response", "summary"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return ExecutionResult(value.strip()[:4000], Outcome.REPORTED_SUCCESS), None
    if not expect_response and (observed := completion_from_trace_result(connection, current, result)):
        return observed
    return ExecutionResult("Home Assistant returned no completion status or spoken summary.", Outcome.UNVERIFIED), None

