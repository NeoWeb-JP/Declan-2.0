"""Resolve early command results while preserving preview priority."""


from preview_timer_orchestration import select_early_result as select_early_result  # Public compatibility export.


def early_command_result(routine_preview, timer_result):
    """Return (reply, outcome) or None, preferring a truthy routine preview."""
    if routine_preview:
        return routine_preview
    if timer_result:
        return timer_result.result.as_legacy_pair()
    return None
