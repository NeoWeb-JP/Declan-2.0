"""Interpret external script outcomes before making execution decisions."""
from dataclasses import dataclass
from enum import StrEnum

from execution_results import Outcome


class ScriptReportedOutcome(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"
    STARTED = "started"
    BUSY = "busy"


@dataclass(frozen=True)
class ScriptProviderResult:
    outcome: ScriptReportedOutcome | None

    def __post_init__(self):
        if self.outcome is not None and not isinstance(self.outcome, ScriptReportedOutcome):
            raise TypeError("outcome must be a ScriptReportedOutcome or None")

    @classmethod
    def parse(cls, value, *, normalize=False) -> "ScriptProviderResult":
        if normalize:
            value = str(value).lower()
        if not isinstance(value, str):
            return cls(None)
        try:
            return cls(ScriptReportedOutcome(value))
        except ValueError:
            return cls(None)

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
