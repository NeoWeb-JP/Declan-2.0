"""Preview-first timer dispatch and typed early-result resolution."""
from execution_results import ExecutionResult


def preview_and_timer(
    phrase, *, source, origin_device, satellite, opener,
    preview_dispatch, detect_phrase, preview_routine,
    timer_dispatch, registry_factory, context_factory,
    matches, handle, guest_mode, decorate,
):
    preview = preview_dispatch(
        phrase, origin_device=origin_device, satellite=satellite,
        detect_phrase=detect_phrase, preview_routine=preview_routine,
    )
    timer = timer_dispatch(
        phrase, source=source, origin_device=origin_device,
        satellite=satellite, routine_preview=preview,
        registry_factory=registry_factory, context_factory=context_factory,
        matches=matches, handle=handle, opener=opener,
        guest_mode=guest_mode, decorate=decorate,
    )
    return preview, timer


def select_early_result(routine_preview, timer_result):
    """Return the typed preview or timer outcome without changing priority."""
    if routine_preview:
        return (routine_preview if isinstance(routine_preview, ExecutionResult)
                else ExecutionResult(*routine_preview))
    if timer_result:
        if not isinstance(timer_result.result, ExecutionResult):
            raise ValueError("Timer dispatch requires a typed execution result")
        return timer_result.result
    return None
