"""Typed interpretation of model responses before decoding proposed actions."""
from dataclasses import dataclass
from enum import StrEnum


class ModelResponseStatus(StrEnum):
    COMPLETED = "completed"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class ModelResponseResult:
    status: ModelResponseStatus
    text: str | None = None

    def __post_init__(self):
        if not isinstance(self.status, ModelResponseStatus):
            raise TypeError("status must be a ModelResponseStatus")
        if self.status is ModelResponseStatus.COMPLETED:
            if not isinstance(self.text, str):
                raise ValueError("Completed model response must contain text")
        elif self.text is not None:
            raise ValueError("Unverified model response cannot contain plan text")

    @classmethod
    def parse(cls, result) -> "ModelResponseResult":
        if result.get("status") != ModelResponseStatus.COMPLETED.value:
            return cls(ModelResponseStatus.UNVERIFIED)
        pieces = [
            part["text"] for item in result["output"]
            if item.get("type") == "message" and item.get("role") == "assistant"
            for part in item.get("content", [])
            if part.get("type") == "output_text"
        ]
        if len(pieces) != 1:
            raise ValueError("Ambiguous model response")
        return cls(ModelResponseStatus.COMPLETED, pieces[0])
