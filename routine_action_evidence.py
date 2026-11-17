"""Typed mapped-routine evidence with explicit legacy mapping adapters."""
from dataclasses import dataclass
from enum import StrEnum


class RoutineActionStatus(StrEnum):
    CONFIRMED = "confirmed"
    ALREADY_SET = "already_set"
    SKIPPED = "skipped"
    FAILED = "failed"
    UNVERIFIED = "unverified"
    PLANNED = "planned"
    REQUESTED = "requested"
    ALREADY_REQUESTED = "already_requested"
    NOT_REQUESTED = "not_requested"
    NOT_CONFIGURED = "not_configured"


@dataclass(frozen=True)
class RoutineActionEvidence:
    target: str
    status: RoutineActionStatus
    action: str | None = None
    entity_id: str | None = None
    detail: str | None = None
    evidence: str | None = None
    observed_at: str | None = None
    required: bool | None = None

    def __post_init__(self):
        object.__setattr__(self, "status", RoutineActionStatus(self.status))
        if not isinstance(self.target, str) or len(self.target) > 240:
            raise ValueError("Routine action target must be bounded text")
        for field in (self.action, self.entity_id, self.detail, self.evidence, self.observed_at):
            if field is not None and (not isinstance(field, str) or len(field) > 240):
                raise ValueError("Routine action evidence fields must be bounded text")
        if self.required is not None and type(self.required) is not bool:
            raise ValueError("Routine action required flag must be a boolean or None")

    @property
    def completed(self):
        return self.status in {RoutineActionStatus.CONFIRMED, RoutineActionStatus.ALREADY_SET}

    def to_wire(self):
        result = {"target": self.target, "status": self.status.value}
        for name in ("action", "entity_id", "detail", "evidence", "observed_at", "required"):
            value = getattr(self, name)
            if value is not None:
                result[name] = value
        return result


def parse_routine_actions(steps):
    """Bound and filter external rows before exposing typed evidence."""
    if isinstance(steps, dict):
        steps = [{"target": target, "status": status} for target, status in steps.items()]
    if not isinstance(steps, list):
        return ()
    results = []
    for step in steps[:200]:
        if not isinstance(step, dict) or not isinstance(step.get("target"), str):
            continue
        try:
            status = RoutineActionStatus(step.get("status"))
        except (ValueError, TypeError):
            continue
        fields = {key: step[key][:240] for key in (
            "target", "action", "entity_id", "detail", "evidence", "observed_at")
            if isinstance(step.get(key), str)}
        if type(step.get("required")) is bool:
            fields["required"] = step["required"]
        results.append(RoutineActionEvidence(status=status, **fields))
    return tuple(results)
