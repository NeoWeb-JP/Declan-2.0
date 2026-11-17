"""Typed lighting-provider evidence with explicit legacy mapping output."""
from dataclasses import dataclass, field
from enum import StrEnum


class LightingActionStatus(StrEnum):
    CONFIRMED = "confirmed"
    ALREADY_SET = "already_set"
    SKIPPED = "skipped"
    FAILED = "failed"
    UNVERIFIED = "unverified"
    PLANNED = "planned"


class LightingActionReason(StrEnum):
    UNRESOLVED = "unresolved"
    AMBIGUOUS = "ambiguous"
    UNAVAILABLE = "unavailable"
    BRIGHTNESS_UNSUPPORTED = "brightness unsupported"
    ALREADY_OFF = "already off"
    BRIGHTNESS_UNKNOWN = "current brightness unknown"
    CONFLICTING_DIRECTIONS = "conflicting directions"
    INCOMPLETE_CORRECTION = "incomplete correction"
    DISPATCH_TIME_LIMIT = "dispatch time limit"
    NO_DISPATCH_RESPONSE = "no dispatch response"


def parse_lighting_reason(value) -> LightingActionReason | None:
    if not isinstance(value, str):
        return None
    try:
        return LightingActionReason(value)
    except ValueError:
        return None


@dataclass(frozen=True)
class LightingActionEvidence:
    target: str
    action: str
    status: LightingActionStatus
    entity_id: str | None = None
    detail: str | None = None
    reason: LightingActionReason | None = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, "status", LightingActionStatus(self.status))
        if not isinstance(self.target, str) or not isinstance(self.action, str):
            raise ValueError("Lighting action target and action must be text")
        if self.entity_id is not None and not isinstance(self.entity_id, str):
            raise ValueError("Lighting action entity ID must be text or None")
        if self.detail is not None and not isinstance(self.detail, str):
            raise ValueError("Lighting action detail must be text or None")
        object.__setattr__(self, "reason", parse_lighting_reason(self.detail))
        if isinstance(self.detail, LightingActionReason):
            object.__setattr__(self, "detail", self.detail.value)

    @property
    def completed(self):
        return self.status in {LightingActionStatus.CONFIRMED, LightingActionStatus.ALREADY_SET}

    def to_wire(self):
        step = {"target": self.target, "action": self.action, "status": self.status.value}
        if self.entity_id is not None:
            step["entity_id"] = self.entity_id
        if self.detail is not None:
            step["detail"] = self.detail
        return step


def confirmed_lighting_entities(steps):
    """Select confirmed follow-up entities from typed or legacy evidence."""
    entities = []
    for step in steps:
        if isinstance(step, LightingActionEvidence):
            if step.completed and step.entity_id is not None:
                entities.append(step.entity_id)
        elif isinstance(step, dict):
            try:
                status = LightingActionStatus(step.get("status"))
            except (ValueError, TypeError):
                continue
            if status in {LightingActionStatus.CONFIRMED, LightingActionStatus.ALREADY_SET} and isinstance(step.get("entity_id"), str):
                entities.append(step["entity_id"])
    return tuple(dict.fromkeys(entities))
