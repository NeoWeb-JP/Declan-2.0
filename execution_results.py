"""Typed results for verified actions; legacy/wire adapters keep public strings stable."""
from dataclasses import dataclass
from enum import StrEnum


class Outcome(StrEnum):
    CONFIRMED = "confirmed"
    PARTIAL = "partial"
    FAILED = "failed"
    UNVERIFIED = "unverified"
    UNRESOLVED = "unresolved"
    NOT_CONFIGURED = "not_configured"
    UNAVAILABLE = "unavailable"
    BUSY = "busy"
    MUSIC_FEEDBACK = "music_feedback"
    SEARCH_RESULT = "search_result"
    TIMER_SET = "timer_set"
    TIMER_ADJUSTED = "timer_adjusted"
    TIMER_CANCELLED = "timer_cancelled"
    TIMER_STOPPED = "timer_stopped"
    TIMER_STATUS = "timer_status"
    NO_TIMER = "no_timer"
    ACTION_ERROR = "action_error"
    PREVIEW = "preview"
    STARTED = "started"
    REQUESTED = "requested"
    REPORTED_SUCCESS = "reported_success"
    EXECUTION_COMPLETED = "execution_completed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"
    SKIPPED = "skipped"
    CONFIRMATION_PROMPT = "confirmation_prompt"
    CONFIRMATION_CANCELLED = "confirmation_cancelled"
    CONFIRMATION_DENIED = "confirmation_denied"


class MovieLaunchStatus(StrEnum):
    SENT = "sent"
    SKIPPED = "skipped"
    FAILED = "failed"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class MovieLaunchResult:
    status: MovieLaunchStatus
    detail: str

    def __post_init__(self):
        object.__setattr__(self, "status", MovieLaunchStatus(self.status))
        if not isinstance(self.detail, str):
            raise ValueError("Movie launch detail must be text")

    def as_legacy_pair(self):
        return self.status.value, self.detail


class ActionStatus(StrEnum):
    CONFIRMED = "confirmed"
    FAILED = "failed"
    UNVERIFIED = "unverified"
    SKIPPED_DEPENDENCY = "skipped_dependency"


DISPATCH_STATUSES = frozenset({
    ActionStatus.CONFIRMED, ActionStatus.FAILED, ActionStatus.UNVERIFIED,
})


@dataclass(frozen=True)
class DispatchResult:
    status: ActionStatus
    detail: str = ""

    def __post_init__(self):
        object.__setattr__(self, "status", ActionStatus(self.status))
        if self.status not in DISPATCH_STATUSES or not isinstance(self.detail, str):
            raise ValueError("Invalid dispatch result")

    @classmethod
    def coerce(cls, value):
        """Accept existing dispatcher tuples only at this compatibility boundary."""
        if isinstance(value, cls):
            return value
        if not isinstance(value, (tuple, list)) or len(value) != 2:
            raise ValueError("Invalid dispatch result")
        return cls(*value)

    def as_legacy_pair(self):
        return self.status.value, self.detail


@dataclass(frozen=True)
class ActionResult:
    index: int
    entity_id: str
    service: str
    status: ActionStatus
    detail: str = ""

    def __post_init__(self):
        object.__setattr__(self, "status", ActionStatus(self.status))
        if not isinstance(self.detail, str):
            raise ValueError("Invalid action detail")

    @property
    def confirmed(self):
        return self.status is ActionStatus.CONFIRMED

    def to_wire(self):
        return {"index": self.index, "entity_id": self.entity_id, "service": self.service,
                "status": self.status.value, "detail": self.detail}


@dataclass(frozen=True)
class ExecutionResult:
    reply: str
    outcome: Outcome
    actions: tuple[ActionResult, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "outcome", Outcome(self.outcome))
        if not isinstance(self.reply, str) or not isinstance(self.actions, tuple) or any(
                not isinstance(action, ActionResult) for action in self.actions):
            raise ValueError("Invalid execution result")

    def as_legacy_pair(self):
        return self.reply, self.outcome.value

    def as_legacy_mapping(self):
        # Existing Python callers consume ActionResult objects in this field.
        return {"reply": self.reply, "outcome": self.outcome.value, "actions": self.actions}

    def to_wire(self):
        return {"reply": self.reply, "outcome": self.outcome.value,
                "actions": [action.to_wire() for action in self.actions]}
