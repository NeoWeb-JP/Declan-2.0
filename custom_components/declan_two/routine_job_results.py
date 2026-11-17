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
