"""Plain tuple views of typed results, for tests that assert reply/outcome pairs.

Production code passes typed results only. These helpers let older tests keep
comparing a typed result with a short tuple such as ("Playing.", "confirmed").
"""
from declan.core.execution_results import ExecutionResult


def pair(value):
    """The tuple a typed result used to be returned as; None stays None."""
    if value is None:
        return None
    if isinstance(value, ExecutionResult):
        return value.reply, value.outcome.value
    if isinstance(value, tuple) and len(value) == 2 and isinstance(value[0], ExecutionResult):
        return value[0].reply, value[0].outcome.value, value[1]
    name = type(value).__name__
    if name == "InventoryResult":
        return value.inventory, value.error.value if value.error is not None else None
    if name in {"ScriptDiscoveryResult", "DiscoveryResult"}:
        return list(value.scripts), value.error.value if value.error is not None else None
    if name == "DeviceStatusResult":
        return value.result.reply, value.result.outcome.value, value.target
    if name == "InformationResult":
        return value.result.reply, value.result.outcome.value, value.category.value
    if name == "ScriptMatchResult":
        if value.status.value == "no_match":
            return None
        return value.status.value, value.selected if value.status.value == "matched" else list(value.candidates)
    if name == "FallbackResponse":
        from declan.ai.action_evidence_wire import action_evidence_to_wire
        return value.result.reply, value.result.outcome.value, list(action_evidence_to_wire(value.action_steps))
    if hasattr(value, "status") and hasattr(value, "detail"):
        return value.status.value, value.detail
    if name == "RoutineSelection":
        from copy import deepcopy
        kind = value.kind.value
        key = {"script": "auto:" + (value.entity_id or ""), "ambiguous": "auto_ambiguous",
               "house_status_missing": "unconfigured_house_status"}.get(kind, value.legacy_key)
        return key, deepcopy(dict(value.options))
    if name == "RoutineTurnSelection":
        return pair(value.routine), value.follow_on
    raise TypeError(f"no tuple view for {name}")


def pair_of(function):
    """Call a typed-result function and return its tuple view."""
    def call(*args, **kwargs):
        return pair(function(*args, **kwargs))
    return call


def follow_on_view(response):
    """A routine follow-on response as plain reply/outcome fields."""
    from types import SimpleNamespace
    return SimpleNamespace(reply=response.result.reply, outcome=response.result.outcome,
                           lighting_context=response.lighting_context,
                           routine_voice_result=pair(response.routine_voice_result))


def execute_follow_on(follow_on, *, routine_reply, routine_outcome, **kwargs):
    """Run a routine follow-on from a plain routine reply/outcome."""
    from declan.turn import routine_follow_on
    return follow_on_view(routine_follow_on.execute_result(
        follow_on, routine_result=ExecutionResult(routine_reply, routine_outcome), **kwargs))
