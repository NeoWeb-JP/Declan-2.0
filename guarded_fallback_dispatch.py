"""Execute guarded AI fallback after local command handlers have declined."""
from dataclasses import dataclass
from execution_results import ExecutionResult


@dataclass(frozen=True)
class FallbackResponse:
    result: ExecutionResult
    action_steps: tuple[dict, ...] = ()

    def __post_init__(self):
        if not isinstance(self.result, ExecutionResult):
            raise ValueError("Fallback response requires a typed execution result")
        if not isinstance(self.action_steps, tuple) or any(
                not isinstance(step, dict) for step in self.action_steps):
            raise ValueError("Fallback action steps must be a tuple of mappings")

    @classmethod
    def coerce(cls, value):
        if isinstance(value, cls):
            return value
        if not isinstance(value, (tuple, list)) or len(value) != 3:
            raise ValueError("Fallback provider requires a typed response or legacy triple")
        reply, outcome, steps = value
        if not isinstance(steps, (tuple, list)):
            raise ValueError("Fallback action steps must be a sequence")
        return cls(ExecutionResult(reply, outcome), tuple(steps))

    def as_legacy_triple(self):
        return self.result.reply, self.result.outcome.value, list(self.action_steps)


def dispatch_fallback_result(message, *, source, exposed_entities, fallback_handler, action_results):
    """Retain typed execution and append validated diagnostic action steps once."""
    fallback = fallback_handler(message, source=source, exposed_entities=exposed_entities)
    if fallback is None:
        return None
    response = FallbackResponse.coerce(fallback)
    action_results.extend(response.action_steps)
    return response.result


def dispatch_fallback(message, *, source, exposed_entities, fallback_handler, action_results):
    """Return a (reply, outcome) pair or None, preserving fallback action steps."""
    fallback = fallback_handler(message, source=source, exposed_entities=exposed_entities)
    if fallback is None:
        return None
    reply, outcome, fallback_steps = fallback
    action_results.extend(fallback_steps)
    return reply, outcome
