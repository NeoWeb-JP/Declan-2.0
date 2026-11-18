"""Information command dispatch and typed response adaptation."""


def dispatch_information_response(
    phrase, *, source, dispatch, adapt, registry_factory, context_factory,
    matches, follow_up, handle, question_context, opener, last_information,
    decorate, guest_mode,
):
    result = dispatch(
        phrase, source=source, registry_factory=registry_factory,
        context_factory=context_factory, matches=matches,
        follow_up=follow_up, handle=handle,
        question_context=question_context, opener=opener,
        last_information=last_information, decorate=decorate,
        guest_mode=guest_mode,
    )
    return adapt(result) if result else None
