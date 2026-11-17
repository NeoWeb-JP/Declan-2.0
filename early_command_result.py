"""Resolve early command results while preserving preview priority."""
from execution_results import ExecutionResult


def select_early_result(routine_preview, timer_result):
    """Keep preview and timer outcomes typed without changing precedence."""
    if routine_preview:
        return (routine_preview if isinstance(routine_preview, ExecutionResult)
                else ExecutionResult(*routine_preview))
    if timer_result:
        if not isinstance(timer_result.result, ExecutionResult):
            raise ValueError("Timer dispatch requires a typed execution result")
        return timer_result.result
    return None


def early_command_result(routine_preview, timer_result):
    """Return (reply, outcome) or None, preferring a truthy routine preview."""
    if routine_preview:
        return routine_preview
    if timer_result:
        return timer_result.result.as_legacy_pair()
    return None
