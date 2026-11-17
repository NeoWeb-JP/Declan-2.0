"""Validate local timer and routine provider contracts at their registry boundary.

Legacy providers may still return tuples. This adapter also accepts typed
ExecutionResult objects without changing the existing HTTP response format.
"""
from execution_results import ExecutionResult


def timer_execution_result(value):
    """Return a validated typed timer result, rejecting malformed provider data."""
    if isinstance(value, ExecutionResult):
        return value
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise ValueError("Timer provider must return a reply/outcome pair")
    return ExecutionResult(*value)


def routine_execution_result(value):
    """Return a typed result and the routine status for legacy or typed providers."""
    if isinstance(value, ExecutionResult):
        return value, None
    if not isinstance(value, (tuple, list)):
        raise ValueError("Routine provider must return a typed result or legacy triple")
    if len(value) == 2 and isinstance(value[0], ExecutionResult):
        result, status = value
    elif len(value) == 3:
        reply, outcome, status = value
        result = ExecutionResult(reply, outcome)
    else:
        raise ValueError("Routine provider must return a typed result or legacy triple")
    if status is not None and not isinstance(status, str):
        raise ValueError("Routine status must be text or None")
    return result, status
