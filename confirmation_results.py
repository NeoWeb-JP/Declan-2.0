"""Validated internal contracts for origin-bound sensitive confirmations."""
from dataclasses import dataclass
from enum import StrEnum
from execution_results import Outcome


class ConfirmationDecision(StrEnum):
    ALLOW = "allow"
    PROMPT = "prompt"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    DENIED = "denied"


@dataclass(frozen=True)
class ConfirmationReplyResult:
    reply: str
    outcome: Outcome
    continue_conversation: bool

    def __post_init__(self):
        if not isinstance(self.reply, str) or not isinstance(self.outcome, Outcome):
            raise TypeError("Confirmation reply requires text and a typed outcome")
        if type(self.continue_conversation) is not bool:
            raise TypeError("Conversation continuation must be a boolean")

    def to_wire(self, session_id):
        return {"reply": self.reply, "session_id": session_id,
                "outcome": self.outcome.value, "continue_conversation": self.continue_conversation}


@dataclass(frozen=True)
class ConfirmationEvaluation:
    decision: ConfirmationDecision
    approved_phrase: str | None = None

    def __post_init__(self):
        object.__setattr__(self, "decision", ConfirmationDecision(self.decision))
        if self.approved_phrase is not None and not isinstance(self.approved_phrase, str):
            raise ValueError("Approved phrase must be text or None")
        if self.decision is ConfirmationDecision.CONFIRMED and not self.approved_phrase:
            raise ValueError("Confirmed action requires an approved phrase")


@dataclass(frozen=True)
class ConfirmationDecisionResult:
    session_id: str
    evaluation: ConfirmationEvaluation

    def __post_init__(self):
        if not isinstance(self.session_id, str) or not self.session_id:
            raise ValueError("Confirmation decision requires a session ID")
        if not isinstance(self.evaluation, ConfirmationEvaluation):
            raise ValueError("Confirmation decision requires a typed evaluation")


@dataclass(frozen=True)
class ConfirmationTurnResult:
    session_id: str | None
    phrase: str
    reply: dict | None
    confirmed: bool

    def __post_init__(self):
        if self.session_id is not None and not isinstance(self.session_id, str):
            raise ValueError("Session ID must be text or None")
        if not isinstance(self.phrase, str) or type(self.confirmed) is not bool:
            raise ValueError("Invalid confirmation turn")
        if self.reply is not None and not isinstance(self.reply, dict):
            raise ValueError("Confirmation reply must be a mapping or None")
        if self.confirmed and self.reply is not None:
            raise ValueError("A blocked confirmation turn cannot execute")
