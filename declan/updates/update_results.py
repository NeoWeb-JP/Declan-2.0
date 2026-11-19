"""Typed updater job interpretation with lossless public status snapshots."""
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any


class UpdateJobState(StrEnum):
    IDLE = "idle"
    INSTALLING = "installing"
    RESTARTING = "restarting"
    FAILED = "failed"


@dataclass(frozen=True)
class UpdateStatusResult:
    _fields: Mapping[str, Any] = field(repr=False)
    state: UpdateJobState | None = field(init=False)

    def __post_init__(self):
        fields = deepcopy(dict(self._fields))
        object.__setattr__(self, "_fields", MappingProxyType(fields))
        raw = fields.get("state")
        try:
            state = UpdateJobState(raw) if isinstance(raw, str) else None
        except ValueError:
            state = None
        object.__setattr__(self, "state", state)

    @property
    def active(self) -> bool:
        return self.state in {UpdateJobState.INSTALLING, UpdateJobState.RESTARTING}

    def to_wire(self) -> dict:
        return deepcopy(dict(self._fields))
