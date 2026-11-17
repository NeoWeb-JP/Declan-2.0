"""Resolve early command results while preserving preview priority."""


def early_command_result(routine_preview, timer_result):
    """Return (reply, outcome) or None, preferring a truthy routine preview."""
    if routine_preview:
        return routine_preview
    if timer_result:
        return timer_result.result.as_legacy_pair()
    return None
