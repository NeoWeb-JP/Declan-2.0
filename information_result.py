"""Typed information-provider execution and response category."""
from dataclasses import dataclass
from enum import StrEnum
from execution_results import ExecutionResult


class InformationCategory(StrEnum):
    TIME = "time"
    WEATHER = "weather"


@dataclass(frozen=True)
class InformationResult:
    result: ExecutionResult
    category: InformationCategory

    def __post_init__(self):
        if not isinstance(self.result, ExecutionResult):
            raise ValueError("Information provider requires a typed execution result")
        object.__setattr__(self, "category", InformationCategory(self.category))

    @classmethod
    def coerce(cls, value):
        if isinstance(value, cls):
            return value
        if type(value) not in (tuple, list) or len(value) != 3:
            raise ValueError("Information provider requires a typed result or legacy triple")
        reply, outcome, category = value
        return cls(ExecutionResult(reply, outcome), category)

    def as_legacy_triple(self):
        return self.result.reply, self.result.outcome.value, self.category.value
