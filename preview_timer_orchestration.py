"""Preview-first timer dispatch orchestration."""


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
