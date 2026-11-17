"""Pure read-only analysis of loaded Home Assistant configuration and traces.

Never evaluate templates or infer device success from a finished trace.
Only identifiers, state summaries and diagnostic codes leave this module.
"""
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
import re
import hashlib
import json

from .routine_job_results import REVIEW_FAILURES, stored_job

IDENTIFIER = re.compile(r"[a-z_][a-z0-9_]*\.[a-z0-9_]+\Z")
SELECTORS = {"entity_id": "entity", "device_id": "device", "area_id": "area"}


class AuditSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class AuditFinding:
    severity: AuditSeverity
    code: str
    path: str
    recommendation: str

    def __post_init__(self):
        if not isinstance(self.severity, AuditSeverity):
            raise TypeError("severity must be an AuditSeverity")
        if any(not isinstance(value, str) for value in (self.code, self.path, self.recommendation)):
            raise TypeError("Audit finding fields must be text")

    def to_wire(self) -> dict:
        return {"severity": self.severity.value, "code": self.code,
                "path": self.path, "recommendation": self.recommendation}


def finding_value(finding, key):
    return getattr(finding, key) if isinstance(finding, AuditFinding) else finding[key]


class TraceOutcome(StrEnum):
    FAILED = "failed"
    PARTIAL = "partial"
    SKIPPED = "skipped"
    RUNNING = "running"
    FINISHED_UNVERIFIED = "finished_unverified"
    CANCELLED = "cancelled"
    UNVERIFIED = "unverified"


class TraceStepStatus(StrEnum):
    FAILED = "failed"
    OBSERVED = "observed"


@dataclass(frozen=True)
class TraceStepEvidence:
    path: str
    status: TraceStepStatus

    def __post_init__(self):
        if not isinstance(self.status, TraceStepStatus):
            raise TypeError("status must be a TraceStepStatus")

    def to_wire(self) -> dict:
        return {"path": self.path, "status": self.status.value}


def trace_step_wire(step):
    return step.to_wire() if isinstance(step, TraceStepEvidence) else dict(step)


def execution_value(execution, key):
    return getattr(execution, key) if isinstance(execution, TraceExecution) else execution[key]


@dataclass(frozen=True)
class TraceExecution:
    status: TraceOutcome
    run_id: Any = None
    start: str | None = None
    finish: str | None = None
    last_step: Any = None
    steps: tuple[TraceStepEvidence | dict, ...] = ()
    steps_truncated: bool = False

    def __post_init__(self):
        if not isinstance(self.status, TraceOutcome):
            raise TypeError("status must be a TraceOutcome")

    def to_wire(self) -> dict:
        return {"run_id": self.run_id, "status": self.status.value,
                "start": self.start, "finish": self.finish, "last_step": self.last_step,
                "steps": [trace_step_wire(step) for step in self.steps], "steps_truncated": self.steps_truncated}


def classify_trace_typed(trace) -> TraceExecution:
    if trace.get("error") or trace.get("script_execution") == "error":
        status = TraceOutcome.FAILED
    elif any((step.status if isinstance(step, TraceStepEvidence) else step["status"]) == TraceStepStatus.FAILED
             for step in trace.get("audit_steps", [])):
        status = TraceOutcome.PARTIAL
    elif trace.get("not_triggered") or trace.get("script_execution") == "failed_conditions":
        status = TraceOutcome.SKIPPED
    elif trace.get("state") == "running":
        status = TraceOutcome.RUNNING
    elif trace.get("script_execution") == "finished":
        status = TraceOutcome.FINISHED_UNVERIFIED
    elif trace.get("script_execution") == "cancelled":
        status = TraceOutcome.CANCELLED
    else:
        status = TraceOutcome.UNVERIFIED
    timestamp = trace.get("timestamp") or {}

    def stamp(value):
        return value.isoformat() if isinstance(value, datetime) else value if isinstance(value, str) else None

    return TraceExecution(status, trace.get("run_id"), stamp(timestamp.get("start")),
                          stamp(timestamp.get("finish")), trace.get("last_step"),
                          tuple(step if isinstance(step, TraceStepEvidence) else dict(step)
                                for step in trace.get("audit_steps", [])[:100]),
                          len(trace.get("audit_steps", [])) > 100)


def review_fingerprint(routine, findings, execution):
    """Review validity follows loaded source and issues, not ordinary run activity."""
    def encode(value):
        if hasattr(value, "template"):
            return value.template
        # HA compiles variables into ScriptVariables instances. Their default
        # repr contains a memory address that changes when scripts are reloaded.
        if isinstance(getattr(value, "variables", None), Mapping):
            return value.variables
        if isinstance(value, (set, frozenset)):
            return sorted(value, key=str)
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)
    relevant = {"entity_id": routine["entity_id"], "config": routine.get("config"),
                "disabled": routine.get("disabled", False),
                "references": {kind: sorted(values, key=str) for kind, values in routine.get("references", {}).items()},
                "findings": sorted([row.to_wire() if isinstance(row, AuditFinding) else row
                                    for row in findings if finding_value(row, "path") != "execution"],
                                   key=lambda row: json.dumps(row, sort_keys=True))}
    if execution and execution_value(execution[0], "status") in {TraceOutcome.FAILED, TraceOutcome.PARTIAL}:
        relevant["latest_failure"] = {key: execution_value(execution[0], key) for key in ("run_id", "status")}
    background = stored_job(routine.get("background_result"))
    if background.outcome in REVIEW_FAILURES:
        relevant["background_failure"] = {key: background.get(key) for key in ("job_id", "outcome")}
    payload = json.dumps(relevant, sort_keys=True, default=encode, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def trace_steps_typed(trace) -> tuple[TraceStepEvidence, ...]:
    """Keep only action paths and error presence, never values or error text."""
    steps = []
    for path, entries in (trace.get("trace") or {}).items():
        if not isinstance(entries, list):
            continue
        failed = any(isinstance(entry, Mapping) and entry.get("error") for entry in entries)
        steps.append(TraceStepEvidence(str(path), TraceStepStatus.FAILED if failed else TraceStepStatus.OBSERVED))
    return tuple(steps)


def trace_steps(trace):
    return [step.to_wire() for step in trace_steps_typed(trace)]


def review_evidence(routine, findings, execution):
    """Separate unchanged source from issues a human has already assessed."""
    source = review_fingerprint({**routine, "background_result": None}, [], [])
    issues = [["finding", finding_value(row, "severity"), finding_value(row, "code"), finding_value(row, "path")]
              for row in findings if finding_value(row, "path") != "execution"]
    issues.extend(["trace", execution_value(row, "run_id"), execution_value(row, "status")] for row in execution
                  if execution_value(row, "status") in {TraceOutcome.FAILED, TraceOutcome.PARTIAL})
    background = stored_job(routine.get("background_result"))
    if background.outcome in REVIEW_FAILURES:
        issues.append(["background", background.get("job_id"), background.get("outcome")])
    return source, sorted({hashlib.sha256(json.dumps(issue, sort_keys=True).encode()).hexdigest()
                           for issue in issues})


def build_report(states, registry, devices, areas, services, routines, traces, gaps=()):
    """Analyze a fresh snapshot; inputs are not modified or persisted."""
    known = set(states) | set(registry)
    items = []
    severity_counts = {severity: 0 for severity in AuditSeverity}
    for routine in sorted(routines, key=lambda row: row["entity_id"]):
        entity_id = routine["entity_id"]
        findings: list[AuditFinding] = []
        dependencies = set()

        def finding(severity, code, path, recommendation):
            row = AuditFinding(severity, code, path, recommendation)
            if row not in findings:
                findings.append(row)

        def reference(kind, value, path):
            if not isinstance(value, str) or any(token in value for token in ("{{", "{%", "{#")):
                finding(AuditSeverity.UNVERIFIED, "dynamic_reference", path,
                        "Review this template in Home Assistant; the audit does not evaluate it.")
                return
            for target in value.split(",") if kind == "entity" else [value]:
                target = target.strip()
                if target in {"all", "none"}:
                    finding(AuditSeverity.UNVERIFIED, "broad_target", path,
                            "Review the targets selected at execution time in Home Assistant.")
                    continue
                dependencies.add((kind, target))
                inventory = known if kind == "entity" else devices if kind == "device" else areas
                if target not in inventory:
                    finding(AuditSeverity.ERROR, "missing_" + kind, path,
                            f"Review missing {kind} {target} in Home Assistant and correct the reference.")
                elif kind == "entity":
                    if registry.get(target, {}).get("disabled"):
                        finding(AuditSeverity.WARNING, "disabled_entity", path,
                                f"Review whether {target} should be enabled or removed from this routine.")
                    elif target not in states:
                        finding(AuditSeverity.WARNING, "entity_without_state", path,
                                f"Check why {target} has no current state in Home Assistant.")
                    elif states[target].get("state") in {"unavailable", "unknown"}:
                        finding(AuditSeverity.WARNING, "unavailable_entity", path,
                                f"Check the integration and availability of {target}.")

        def walk(value, path="config", depth=0, inspect_dependencies=True):
            if depth > 40:
                finding(AuditSeverity.UNVERIFIED, "inspection_depth", path,
                        "Inspect deeply nested configuration in Home Assistant.")
                return
            if isinstance(value, Mapping):
                if inspect_dependencies and value.get("enabled") is False:
                    return
                for key, child in value.items():
                    child_path = path + "." + str(key)
                    if inspect_dependencies and key in SELECTORS:
                        for target in child if isinstance(child, (list, tuple)) else [child]:
                            reference(SELECTORS[key], target, child_path)
                    elif inspect_dependencies and key in {"service", "action"} and isinstance(child, str):
                        if IDENTIFIER.fullmatch(child):
                            dependencies.add(("service", child))
                            if child not in services:
                                finding(AuditSeverity.ERROR, "missing_service", child_path,
                                        f"Check that service {child} is registered in Home Assistant.")
                            if child.startswith("script.") and child not in {"script.turn_on", "script.turn_off", "script.toggle", "script.reload"}:
                                reference("entity", child, child_path)
                        else:
                            finding(AuditSeverity.UNVERIFIED, "dynamic_service", child_path,
                                    "Review the service selected at runtime in Home Assistant.")
                    elif isinstance(child, str) and any(token in child for token in ("{{", "{%", "{#")):
                        finding(AuditSeverity.UNVERIFIED, "template_not_evaluated", child_path,
                                "Review template dependencies and execution traces in Home Assistant.")
                    else:
                        # Variable payloads describe data, including returned step
                        # labels named "action". They are not executable services.
                        walk(child, child_path, depth + 1,
                             inspect_dependencies and key not in {"variables", "fields", "metadata"})
            elif isinstance(value, (list, tuple)):
                for index, child in enumerate(value):
                    walk(child, f"{path}[{index}]", depth + 1, inspect_dependencies)

        config = routine.get("config")
        if isinstance(config, Mapping):
            walk(config)
        else:
            finding(AuditSeverity.UNVERIFIED, "configuration_unavailable", "config",
                    "Check the loaded configuration in Home Assistant; dependency inspection is incomplete.")
        for kind, values in routine.get("references", {}).items():
            for value in values:
                reference(kind, value, "loaded_references." + kind)
        if routine.get("state") in {"unavailable", "unknown"}:
            finding(AuditSeverity.WARNING, "routine_unavailable", "state", "Check this routine's integration in Home Assistant.")
        if routine.get("disabled"):
            finding(AuditSeverity.WARNING, "routine_disabled", "state", "Review whether this routine should remain disabled.")
        execution = []
        for trace in traces.get(entity_id, []):
            execution.append(classify_trace_typed(trace))
        execution.sort(key=lambda row: row.start or "", reverse=True)
        execution = execution[:5]
        if not execution:
            finding(AuditSeverity.UNVERIFIED, "no_trace", "execution",
                    "No retained trace is available. Review a future normal run in Home Assistant.")
        elif any(row.status in {TraceOutcome.FAILED, TraceOutcome.PARTIAL} for row in execution):
            finding(AuditSeverity.ERROR, "execution_failed", "execution",
                    "Open the corresponding run in Home Assistant Traces to inspect the failing action.")
        review_source, review_issues = review_evidence(routine, findings, execution)
        if not routine.get("stale"):
            for row in findings:
                severity_counts[row.severity] += 1
        items.append({"entity_id": entity_id, "name": routine.get("name") or entity_id,
                      "review_source": review_source, "review_issues": review_issues,
                      "background_result": stored_job(routine["background_result"]).to_wire()
                          if routine.get("background_result") is not None else None,
                      "editor_path": routine.get("editor_path"),
                      "stale": bool(routine.get("stale")),
                      "yaml_available": bool(routine.get("yaml_available")),
                      "fingerprint": review_fingerprint(routine, findings, execution),
                      "state": routine.get("state"), "disabled": bool(routine.get("disabled")),
                      "dependencies": [{"kind": kind, "id": target} for kind, target in sorted(dependencies)],
                      "findings": [row.to_wire() for row in findings], "executions": [row.to_wire() for row in execution]})
    stale_ids = {row["entity_id"] for row in items if row["stale"]}
    entities = [{"entity_id": key, "name": states.get(key, {}).get("name") or key,
                 "stale": key in stale_ids,
                 "state": states.get(key, {}).get("state"),
                 "disabled": bool(registry.get(key, {}).get("disabled"))} for key in sorted(known)]
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "read_only": True,
            "coverage": "partial" if gaps or any(
                f["code"] == "configuration_unavailable" for row in items for f in row["findings"]
            ) else "available_loaded_sources",
            "gaps": list(gaps), "routines": items, "entities": entities,
            "summary": {"scripts": sum(r["entity_id"].startswith("script.") and not r["stale"] for r in items),
                        "automations": sum(r["entity_id"].startswith("automation.") and not r["stale"] for r in items),
                        "stale": len(stale_ids),
                        "entities": len(entities),
                        **{severity.value: count for severity, count in severity_counts.items()}}}
