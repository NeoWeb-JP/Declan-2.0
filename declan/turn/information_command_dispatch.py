"""Dispatch information questions before device and lighting commands."""


def dispatch_information(phrase, *, source, registry_factory, context_factory,
                         matches, follow_up, handle, question_context, opener,
                         last_information, decorate, guest_mode):
    """Return the information registry result, preserving existing dependencies."""
    registry = registry_factory(matches=matches, follow_up=follow_up,
        handle=handle, question_context=question_context, opener=opener,
        last_information=last_information, decorate=decorate, guest_mode=guest_mode)
    return registry.dispatch(context_factory(phrase=phrase, source=source))
