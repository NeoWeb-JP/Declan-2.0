"""Interpret external script outcomes before making execution decisions."""
from dataclasses import dataclass
from enum import StrEnum

from declan.core.execution_results import Outcome


class BackgroundReceiptStatus(StrEnum):
    ACCEPTED = "accepted"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class BackgroundReceiptResult:
    status: BackgroundReceiptStatus

    def __post_init__(self):
        if not isinstance(self.status, BackgroundReceiptStatus):
            raise TypeError("status must be a BackgroundReceiptStatus")

    @classmethod
    def parse(cls, http_status, payload, *, job_id, entity_id) -> "BackgroundReceiptResult":
        """Accept only a durable receipt correlated to this exact request."""
        accepted = (http_status == 202 and isinstance(payload, dict)
                    and payload.get("status") == BackgroundReceiptStatus.ACCEPTED.value
                    and payload.get("job_id") == job_id
                    and payload.get("entity_id") == entity_id)
        return cls(BackgroundReceiptStatus.ACCEPTED if accepted else BackgroundReceiptStatus.UNVERIFIED)


class ScriptReportedOutcome(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"
    STARTED = "started"
    BUSY = "busy"


class ScriptReason(StrEnum):
    SCREEN_MOVING = "screen_moving"
    SCREEN_POSITION_UNVERIFIED = "screen_position_unverified"
    REQUESTED_ACTION_INVALID = "requested_action_missing_or_invalid"


@dataclass(frozen=True)
class ScriptProviderResult:
    outcome: ScriptReportedOutcome | None
    reason: ScriptReason | None = None

    def __post_init__(self):
        if self.outcome is not None and not isinstance(self.outcome, ScriptReportedOutcome):
            raise TypeError("outcome must be a ScriptReportedOutcome or None")
        if self.reason is not None and not isinstance(self.reason, ScriptReason):
            raise TypeError("reason must be a ScriptReason or None")

    @classmethod
    def parse(cls, value, *, normalize=False, reason=None) -> "ScriptProviderResult":
        try:
            parsed_reason = ScriptReason(reason) if isinstance(reason, str) else None
        except ValueError:
            parsed_reason = None
        if normalize:
            value = str(value).lower()
        if not isinstance(value, str):
            return cls(None, parsed_reason)
        try:
            return cls(ScriptReportedOutcome(value), parsed_reason)
        except ValueError:
            return cls(None, parsed_reason)

    @property
    def guard_reason(self) -> ScriptReason | None:
        if self.outcome in {ScriptReportedOutcome.UNKNOWN, ScriptReportedOutcome.BUSY}:
            return self.reason
        return None

    @property
    def execution_outcome(self) -> Outcome:
        if self.outcome is None:
            return Outcome.UNVERIFIED
        return {ScriptReportedOutcome.SUCCESS: Outcome.REPORTED_SUCCESS,
                ScriptReportedOutcome.PARTIAL: Outcome.PARTIAL,
                ScriptReportedOutcome.FAILED: Outcome.FAILED,
                ScriptReportedOutcome.CANCELLED: Outcome.CANCELLED,
                ScriptReportedOutcome.STARTED: Outcome.STARTED,
                ScriptReportedOutcome.BUSY: Outcome.BUSY}.get(self.outcome, Outcome.UNVERIFIED)


class TraceProviderOutcome(StrEnum):
    FINISHED_UNVERIFIED = "finished_unverified"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RUNNING = "running"
    SKIPPED = "skipped"
    UNVERIFIED = "unverified"


def parse_trace_outcome(value) -> TraceProviderOutcome | None:
    if not isinstance(value, str):
        return None
    try:
        return TraceProviderOutcome(value)
    except ValueError:
        return None


@dataclass(frozen=True)
class CorrelatedTraceResult:
    status: TraceProviderOutcome | None
    run_id: str

    def __post_init__(self):
        if self.status is not None and not isinstance(self.status, TraceProviderOutcome):
            raise TypeError("status must be a TraceProviderOutcome or None")
        if not isinstance(self.run_id, str) or not self.run_id:
            raise ValueError("Correlated trace requires a run ID")

    @classmethod
    def parse(cls, evidence, *, entity_id, context_id) -> "CorrelatedTraceResult | None":
        if (not isinstance(evidence, dict) or evidence.get("entity_id") != entity_id
                or evidence.get("context_id") != context_id or evidence.get("evidence") != "ha_trace"
                or not isinstance(evidence.get("run_id"), str) or not evidence["run_id"]):
            return None
        return cls(parse_trace_outcome(evidence.get("status")), evidence["run_id"])

    @property
    def detail(self) -> str:
        return "HA trace " + self.run_id[:128] + "; device results not verified."
