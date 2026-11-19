"""Select preview and timer results before command dispatch."""
from declan.timers import preview_timer_orchestration


def resolve(phrase, *, source, origin_device, satellite, opener,
            preview_dispatch, detect_phrase, preview_routine,
            timer_dispatch, registry_factory, context_factory,
            matches, handle, guest_mode, decorate):
    preview, timer = preview_timer_orchestration.preview_and_timer(
        phrase, source=source, origin_device=origin_device,
        satellite=satellite, opener=opener,
        preview_dispatch=preview_dispatch, detect_phrase=detect_phrase,
        preview_routine=preview_routine, timer_dispatch=timer_dispatch,
        registry_factory=registry_factory, context_factory=context_factory,
        matches=matches, handle=handle, guest_mode=guest_mode,
        decorate=decorate,
    )
    return preview_timer_orchestration.select_early_result(preview, timer)
