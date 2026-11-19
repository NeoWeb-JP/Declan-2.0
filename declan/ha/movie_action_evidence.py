"""Typed app-launch evidence retains acceptance versus completion semantics."""
from dataclasses import dataclass
from declan.core.execution_results import MovieLaunchStatus


@dataclass(frozen=True)
class MovieActionEvidence:
    target: str
    status: MovieLaunchStatus
    entity_id: str
    detail: str

    def __post_init__(self):
        object.__setattr__(self, "status", MovieLaunchStatus(self.status))
        if any(not isinstance(value, str) for value in (self.target, self.entity_id, self.detail)):
            raise ValueError("Movie action evidence fields must be text")

    def to_wire(self):
        return {"target": self.target, "action": "open_app", "status": self.status.value,
                "entity_id": self.entity_id, "detail": self.detail}
