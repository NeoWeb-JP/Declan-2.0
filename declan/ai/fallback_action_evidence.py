"""Typed fallback diagnostic projection with explicit detail redaction."""
from dataclasses import dataclass
from execution_results import ActionResult, ActionStatus


@dataclass(frozen=True)
class FallbackActionEvidence:
    entity_id: str
    action: str
    status: ActionStatus
    detail: str | None = None

    def __post_init__(self):
        object.__setattr__(self, "status", ActionStatus(self.status))
        if not isinstance(self.entity_id, str) or not isinstance(self.action, str):
            raise ValueError("Fallback evidence entity and action must be text")
        if self.detail is not None and not isinstance(self.detail, str):
            raise ValueError("Fallback evidence detail must be text or None")

    @classmethod
    def from_action(cls, action, *, include_detail):
        if not isinstance(action, ActionResult) or type(include_detail) is not bool:
            raise ValueError("Fallback projection requires typed action evidence and a detail policy")
        return cls(action.entity_id, action.service, action.status,
                   action.detail if include_detail else None)

    @property
    def ai_generated(self):
        return True

    def to_wire(self):
        step = {"entity_id": self.entity_id, "action": self.action,
                "ai_generated": True, "status": self.status.value}
        if self.detail is not None:
            step["detail"] = self.detail
        return step
