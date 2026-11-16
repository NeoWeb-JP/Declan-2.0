"""Pure read-only analysis of loaded Home Assistant configuration and traces.

Never evaluate templates or infer device success from a finished trace.
Only identifiers, state summaries and diagnostic codes leave this module.
"""
from collections.abc import Mapping
from datetime import datetime, timezone
import re
import hashlib
import json

IDENTIFIER = re.compile(r"[a-z_][a-z0-9_]*\.[a-z0-9_]+\Z")
SELECTORS = {"entity_id": "entity", "device_id": "device", "area_id": "area"}


def review_fingerprint(routine, findings, execution):
    """Review validity follows loaded source and issues, not ordinary run activity."""
    def encode(value):
        if hasattr(value, "template"):
            return value.template
        if isinstance(value, (set, frozenset)):
            return sorted(value, key=str)
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)
    relevant = {"entity_id": routine["entity_id"], "config": routine.get("config"),
                "disabled": routine.get("disabled", False),
                "references": {kind: sorted(values, key=str) for kind, values in routine.get("references", {}).items()},
                "findings": sorted([row for row in findings if row["path"] != "execution"], key=lambda row: json.dumps(row, sort_keys=True))}
    if execution and execution[0]["status"] in {"failed", "partial"}:
        relevant["latest_failure"] = {key: execution[0][key] for key in ("run_id", "status")}
    payload = json.dumps(relevant, sort_keys=True, default=encode, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def trace_steps(trace):
    """Keep only action paths and error presence, never values or error text."""
    steps = []
    for path, entries in (trace.get("trace") or {}).items():
        if not isinstance(entries, list):
            continue
        failed = any(isinstance(entry, Mapping) and entry.get("error") for entry in entries)
        steps.append({"path": str(path), "status": "failed" if failed else "observed"})
    return steps


def build_report(states, registry, devices, areas, services, routines, traces, gaps=()):
    """Analyze a fresh snapshot; inputs are not modified or persisted."""
    known = set(states) | set(registry)
    items = []
    for routine in sorted(routines, key=lambda row: row["entity_id"]):
        entity_id = routine["entity_id"]
        findings = []
        dependencies = set()

        def finding(severity, code, path, recommendation):
            row = {"severity": severity, "code": code, "path": path,
                   "recommendation": recommendation}
            if row not in findings:
                findings.append(row)

        def reference(kind, value, path):
            if not isinstance(value, str) or any(token in value for token in ("{{", "{%", "{#")):
                finding("unverified", "dynamic_reference", path,
                        "Review this template in Home Assistant; the audit does not evaluate it.")
                return
            for target in value.split(",") if kind == "entity" else [value]:
                target = target.strip()
                if target in {"all", "none"}:
                    finding("unverified", "broad_target", path,
                            "Review the targets selected at execution time in Home Assistant.")
                    continue
                dependencies.add((kind, target))
                inventory = known if kind == "entity" else devices if kind == "device" else areas
                if target not in inventory:
                    finding("error", "missing_" + kind, path,
                            f"Review missing {kind} {target} in Home Assistant and correct the reference.")
                elif kind == "entity":
                    if registry.get(target, {}).get("disabled"):
                        finding("warning", "disabled_entity", path,
                                f"Review whether {target} should be enabled or removed from this routine.")
                    elif target not in states:
                        finding("warning", "entity_without_state", path,
                                f"Check why {target} has no current state in Home Assistant.")
                    elif states[target].get("state") in {"unavailable", "unknown"}:
                        finding("warning", "unavailable_entity", path,
                                f"Check the integration and availability of {target}.")

        def walk(value, path="config", depth=0):
            if depth > 40:
                finding("unverified", "inspection_depth", path,
                        "Inspect deeply nested configuration in Home Assistant.")
                return
            if isinstance(value, Mapping):
                if value.get("enabled") is False:
                    return
                for key, child in value.items():
                    child_path = path + "." + str(key)
                    if key in SELECTORS:
                        for target in child if isinstance(child, (list, tuple)) else [child]:
                            reference(SELECTORS[key], target, child_path)
                    elif key in {"service", "action"} and isinstance(child, str):
                        if IDENTIFIER.fullmatch(child):
                            dependencies.add(("service", child))
                            if child not in services:
                                finding("error", "missing_service", child_path,
                                        f"Check that service {child} is registered in Home Assistant.")
                            if child.startswith("script.") and child not in {"script.turn_on", "script.turn_off", "script.toggle", "script.reload"}:
                                reference("entity", child, child_path)
                        else:
                            finding("unverified", "dynamic_service", child_path,
                                    "Review the service selected at runtime in Home Assistant.")
                    elif isinstance(child, str) and any(token in child for token in ("{{", "{%", "{#")):
                        finding("unverified", "template_not_evaluated", child_path,
                                "Review template dependencies and execution traces in Home Assistant.")
                    else:
                        walk(child, child_path, depth + 1)
            elif isinstance(value, (list, tuple)):
                for index, child in enumerate(value):
                    walk(child, f"{path}[{index}]", depth + 1)

        config = routine.get("config")
        if isinstance(config, Mapping):
            walk(config)
        else:
            finding("unverified", "configuration_unavailable", "config",
                    "Check the loaded configuration in Home Assistant; dependency inspection is incomplete.")
        for kind, values in routine.get("references", {}).items():
            for value in values:
                reference(kind, value, "loaded_references." + kind)
        if routine.get("state") in {"unavailable", "unknown"}:
            finding("warning", "routine_unavailable", "state", "Check this routine's integration in Home Assistant.")
        if routine.get("disabled"):
            finding("warning", "routine_disabled", "state", "Review whether this routine should remain disabled.")
        execution = []
        for trace in traces.get(entity_id, []):
            if trace.get("error") or trace.get("script_execution") == "error":
                status = "failed"
            elif any(step["status"] == "failed" for step in trace.get("audit_steps", [])):
                status = "partial"
            elif trace.get("not_triggered") or trace.get("script_execution") == "failed_conditions":
                status = "skipped"
            elif trace.get("state") == "running":
                status = "running"
            elif trace.get("script_execution") == "finished":
                status = "finished_unverified"
            elif trace.get("script_execution") == "cancelled":
                status = "cancelled"
            else:
                status = "unverified"
            timestamp = trace.get("timestamp") or {}
            def stamp(value):
                return value.isoformat() if isinstance(value, datetime) else value if isinstance(value, str) else None
            execution.append({"run_id": trace.get("run_id"), "status": status,
                              "start": stamp(timestamp.get("start")), "finish": stamp(timestamp.get("finish")),
                              "last_step": trace.get("last_step"),
                              "steps": trace.get("audit_steps", [])[:100],
                              "steps_truncated": len(trace.get("audit_steps", [])) > 100})
        execution.sort(key=lambda row: row.get("start") or "", reverse=True)
        execution = execution[:5]
        if not execution:
            finding("unverified", "no_trace", "execution",
                    "No retained trace is available. Review a future normal run in Home Assistant.")
        elif any(row["status"] in {"failed", "partial"} for row in execution):
            finding("error", "execution_failed", "execution",
                    "Open the corresponding run in Home Assistant Traces to inspect the failing action.")
        items.append({"entity_id": entity_id, "name": routine.get("name") or entity_id,
                      "stale": bool(routine.get("stale")),
                      "yaml_available": bool(routine.get("yaml_available")),
                      "fingerprint": review_fingerprint(routine, findings, execution),
                      "state": routine.get("state"), "disabled": bool(routine.get("disabled")),
                      "dependencies": [{"kind": kind, "id": target} for kind, target in sorted(dependencies)],
                      "findings": findings, "executions": execution})
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
                        **{severity: sum(f["severity"] == severity for r in items if not r["stale"] for f in r["findings"])
                           for severity in ("error", "warning", "unverified")}}}
