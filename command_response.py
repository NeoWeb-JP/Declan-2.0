"""Typed dispatched responses with the context needed by turn orchestration."""
from dataclasses import dataclass

from execution_results import ExecutionResult


@dataclass(frozen=True)
class CommandResponse:
    result: ExecutionResult
    routine_status: str | None = None
    information_context: object = None
    status_target: str | None = None
    lighting_context: tuple[str, ...] = ()
    routine_voice_result: ExecutionResult | None = None

    def __post_init__(self):
        if not isinstance(self.result, ExecutionResult):
            raise ValueError("Command response requires a typed execution result")
        if self.routine_status is not None and not isinstance(self.routine_status, str):
            raise ValueError("Routine status must be text or None")
        if self.status_target is not None and not isinstance(self.status_target, str):
            raise ValueError("Status target must be text or None")
        if not isinstance(self.lighting_context, tuple) or any(
                not isinstance(entity, str) for entity in self.lighting_context):
            raise ValueError("Lighting context must be a tuple of entity IDs")
        if self.routine_voice_result is not None and not isinstance(self.routine_voice_result, ExecutionResult):
            raise ValueError("Routine voice result must be typed or None")
