"""Dispatch routine preview requests without executing other commands."""
from execution_results import ExecutionResult


def dispatch_preview_result(phrase, *, origin_device, satellite, detect_phrase, preview_routine):
    """Retain validated typed preview outcomes without executing a routine."""
    result = dispatch_preview(phrase, origin_device=origin_device, satellite=satellite,
                              detect_phrase=detect_phrase, preview_routine=preview_routine)
    if result is None:
        return None
    if isinstance(result, ExecutionResult):
        return result
    if not isinstance(result, (tuple, list)) or len(result) != 2:
        raise ValueError("Routine preview requires a typed result or legacy pair")
    return ExecutionResult(*result)


def dispatch_preview(phrase, *, origin_device, satellite, detect_phrase, preview_routine):
    """Return the preview result or None when the phrase is not a preview."""
    preview_phrase = detect_phrase(phrase)
    if not preview_phrase:
        return None
    return preview_routine(preview_phrase, origin_device or satellite)
