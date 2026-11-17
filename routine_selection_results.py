"""Typed routine selection with explicit adapters for legacy selection tuples."""
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any


class RoutineSelectionKind(StrEnum):
    SCRIPT = "script"
    AMBIGUOUS = "ambiguous"
    HOUSE_STATUS_MISSING = "house_status_missing"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class RoutineSelection:
    kind: RoutineSelectionKind
    entity_id: str | None = None
    options: Mapping[str, Any] = field(default_factory=dict)
    legacy_key: str = ""

    def __post_init__(self):
        if not isinstance(self.kind, RoutineSelectionKind):
            raise TypeError("routine selection kind must be a RoutineSelectionKind")
        if self.kind is RoutineSelectionKind.SCRIPT and not isinstance(self.entity_id, str):
            raise ValueError("script selection requires an entity ID")
        if not isinstance(self.options, Mapping):
            raise TypeError("routine selection options must be a mapping")
        object.__setattr__(self, "options", MappingProxyType(deepcopy(dict(self.options))))

    def __deepcopy__(self, memo):
        result = RoutineSelection(self.kind, self.entity_id, self.options, self.legacy_key)
        memo[id(self)] = result
        return result

    def as_legacy_pair(self):
        key = {RoutineSelectionKind.SCRIPT: "auto:" + (self.entity_id or ""),
               RoutineSelectionKind.AMBIGUOUS: "auto_ambiguous",
               RoutineSelectionKind.HOUSE_STATUS_MISSING: "unconfigured_house_status",
               RoutineSelectionKind.UNSUPPORTED: self.legacy_key}[self.kind]
        return key, deepcopy(dict(self.options))

    @classmethod
    def coerce(cls, value) -> 'RoutineSelection':
        if isinstance(value, cls):
            return value
        key, options = value
        if key.startswith("auto:"):
            return cls(RoutineSelectionKind.SCRIPT, key[5:], options)
        if key == "auto_ambiguous":
            return cls(RoutineSelectionKind.AMBIGUOUS, options=options)
        if key == "unconfigured_house_status":
            return cls(RoutineSelectionKind.HOUSE_STATUS_MISSING, options=options)
        return cls(RoutineSelectionKind.UNSUPPORTED, options=options, legacy_key=key)


@dataclass(frozen=True)
class RoutineTurnSelection:
    routine: RoutineSelection
    follow_on: str | None = None

    def __post_init__(self):
        if not isinstance(self.routine, RoutineSelection):
            raise TypeError("routine turn requires a typed selection")

    def as_legacy_pair(self):
        return self.routine.as_legacy_pair(), self.follow_on

    @classmethod
    def coerce(cls, value) -> 'RoutineTurnSelection':
        if isinstance(value, cls):
            return value
        routine, follow_on = value
        return cls(RoutineSelection.coerce(routine), follow_on)
