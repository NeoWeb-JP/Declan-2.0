"""Typed final-turn metadata with an explicit response-mapping adapter."""
from dataclasses import dataclass

from execution_results import Outcome


@dataclass(frozen=True)
class TurnResponse:
    session_response: dict
    outcome: Outcome | None = None
    routine_status: str | None = None

    def __post_init__(self):
        if not isinstance(self.session_response, dict) or not isinstance(self.session_response.get("session_id"), str):
            raise ValueError("Turn response requires a session response")
        if not isinstance(self.session_response.get("reply"), str):
            raise ValueError("Turn response requires spoken response text")
        if self.outcome is not None:
            object.__setattr__(self, "outcome", Outcome(self.outcome))
        if self.routine_status is not None and not isinstance(self.routine_status, str):
            raise ValueError("Routine status must be text or None")

    def to_wire(self, apply_outcome_metadata=None):
        reply = dict(self.session_response)
        if apply_outcome_metadata is not None:
            apply_outcome_metadata(reply, outcome=self.outcome, routine_status=self.routine_status)
        if self.outcome is not None:
            reply["outcome"] = self.outcome.value
        if self.routine_status:
            reply["routine_status"] = self.routine_status
        return reply
