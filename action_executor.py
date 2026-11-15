"""Deterministic action executor for *already authorised* HA action plans.

The caller must supply a trusted dispatcher that enforces HA permissions and
returns a verified result. This module never makes HTTP requests itself.
"""
from dataclasses import dataclass
from action_plan import CandidateAction


@dataclass(frozen=True)
class ActionResult:
    index: int
    entity_id: str
    service: str
    status: str
    detail: str = ""


def execute_verified(plan, dispatcher):
    """Execute in order, skip failed dependencies, continue independent steps.

    dispatcher(action) must return (status, detail) where status is one of
    'confirmed', 'failed', 'unverified'. An HTTP 200 alone is not confirmation.
    """
    if not isinstance(plan, tuple) or not all(isinstance(x, CandidateAction) for x in plan):
        raise ValueError("Plan has not been validated")
    if not callable(dispatcher):
        raise ValueError("Trusted dispatcher is required")
    results = []
    for index, action in enumerate(plan):
        if any(results[dep].status != "confirmed" for dep in action.depends_on):
            results.append(ActionResult(index, action.entity_id, action.service, "skipped_dependency"))
            continue
        try:
            status, detail = dispatcher(action)
            if status not in {"confirmed", "failed", "unverified"}:
                raise ValueError("Invalid dispatch status")
            if not isinstance(detail, str):
                raise ValueError("Invalid dispatch detail")
        except Exception:
            # Do not expose sensitive HA internals to voice responses.
            status, detail = "failed", "Dispatch or verification failed"
        results.append(ActionResult(index, action.entity_id, action.service, status, detail[:240]))
    return tuple(results)


def summarise(results):
    """Never claim success for unverified dispatches."""
    counts = {key: sum(x.status == key for x in results)
              for key in ("confirmed", "failed", "unverified", "skipped_dependency")}
    if not results:
        return "No actions were performed.", "unresolved"
    if counts["confirmed"] == len(results):
        return "All requested actions were confirmed.", "confirmed"
    if counts["confirmed"]:
        return (f"{counts['confirmed']} confirmed, {counts['failed']} failed, "
                f"{counts['unverified']} unverified and {counts['skipped_dependency']} skipped."), "partial"
    return (f"No actions confirmed: {counts['failed']} failed, "
            f"{counts['unverified']} unverified and {counts['skipped_dependency']} skipped."), "unverified"
