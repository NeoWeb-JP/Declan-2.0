"""Typed interpretation of durable routine jobs, with lossless wire adapters."""
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any


class RoutineJobOutcome(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    REPORTED_SUCCESS = "reported_success"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BUSY = "busy"
    UNVERIFIED = "unverified"
    FINISHED_UNVERIFIED = "finished_unverified"
    SKIPPED = "skipped"


class ScriptReportedOutcome(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BUSY = "busy"
    UNKNOWN = "unknown"
    STARTED = "started"


@dataclass(frozen=True)
class ScriptReportedResult:
    outcome: ScriptReportedOutcome | None

    def __post_init__(self):
        if self.outcome is not None and not isinstance(self.outcome, ScriptReportedOutcome):
            raise TypeError("outcome must be a ScriptReportedOutcome or None")

    @classmethod
    def parse(cls, value) -> "ScriptReportedResult":
        if not isinstance(value, str):
            return cls(None)
        try:
            return cls(ScriptReportedOutcome(value))
        except ValueError:
            return cls(None)

    @property
    def job_outcome(self) -> RoutineJobOutcome:
        if self.outcome is None:
            return RoutineJobOutcome.UNVERIFIED
        return {ScriptReportedOutcome.SUCCESS: RoutineJobOutcome.REPORTED_SUCCESS,
                ScriptReportedOutcome.PARTIAL: RoutineJobOutcome.PARTIAL,
                ScriptReportedOutcome.FAILED: RoutineJobOutcome.FAILED,
                ScriptReportedOutcome.CANCELLED: RoutineJobOutcome.CANCELLED,
                ScriptReportedOutcome.BUSY: RoutineJobOutcome.BUSY}.get(self.outcome, RoutineJobOutcome.UNVERIFIED)


class RoutineJobStepStatus(StrEnum):
    CONFIRMED = "confirmed"
    ALREADY_SET = "already_set"
    FAILED = "failed"
    UNVERIFIED = "unverified"
    UNAVAILABLE = "unavailable"
    SKIPPED = "skipped"
    PLANNED = "planned"
    REQUESTED = "requested"
    ALREADY_REQUESTED = "already_requested"
    NOT_REQUESTED = "not_requested"
    NOT_CONFIGURED = "not_configured"
    OBSERVED = "observed"


@dataclass(frozen=True)
class RoutineJobStepEvidence:
    status: RoutineJobStepStatus | None
    fields: tuple[tuple[str, str], ...]
    required: bool
    requires_completion: bool

    def __post_init__(self):
        if self.status is not None and not isinstance(self.status, RoutineJobStepStatus):
            raise TypeError('step status must be a RoutineJobStepStatus or None')
        if not isinstance(self.fields, tuple) or any(
                not isinstance(pair, tuple) or len(pair) != 2
                or pair[0] not in {'target', 'action', 'entity_id', 'status'}
                or not isinstance(pair[1], str) or len(pair[1]) > 240 for pair in self.fields):
            raise ValueError('step fields must be bounded projected text')
        if type(self.required) is not bool or type(self.requires_completion) is not bool:
            raise TypeError('step required flags must be booleans')

    @classmethod
    def from_mapping(cls, step) -> 'RoutineJobStepEvidence':
        value = step.get('status')
        try:
            status = RoutineJobStepStatus(value) if isinstance(value, str) else None
        except ValueError:
            status = None
        fields = tuple((key, step[key][:240]) for key in ('target', 'action', 'entity_id', 'status')
                       if isinstance(step.get(key), str))
        return cls(status, fields, step.get('required', True) is not False, bool(step.get('required', True)))

    @property
    def completed(self) -> bool:
        return self.status in {RoutineJobStepStatus.CONFIRMED, RoutineJobStepStatus.ALREADY_SET}

    def to_wire(self) -> dict:
        return {**dict(self.fields), 'required': self.required}


def job_outcome(value) -> RoutineJobOutcome | None:
    if not isinstance(value, str):
        return None
    try:
        return RoutineJobOutcome(value)
    except ValueError:
        return None


@dataclass(frozen=True)
class StoredRoutineJob:
    _fields: Mapping[str, Any] = field(repr=False)
    outcome: RoutineJobOutcome | None = field(init=False)

    def __post_init__(self):
        fields = deepcopy(dict(self._fields))
        object.__setattr__(self, "_fields", MappingProxyType(fields))
        object.__setattr__(self, "outcome", job_outcome(fields.get("outcome")))

    def get(self, key, default=None):
        return deepcopy(self._fields.get(key, default))

    def to_wire(self) -> dict:
        return deepcopy(dict(self._fields))

    def __deepcopy__(self, memo):
        snapshot = StoredRoutineJob(self._fields)
        memo[id(self)] = snapshot
        return snapshot


def stored_job(value) -> StoredRoutineJob:
    return value if isinstance(value, StoredRoutineJob) else StoredRoutineJob(value or {})


REVIEW_FAILURES = frozenset({RoutineJobOutcome.FAILED, RoutineJobOutcome.PARTIAL,
                           RoutineJobOutcome.UNVERIFIED, RoutineJobOutcome.CANCELLED})
