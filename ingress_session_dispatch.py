"""Capture arbitration, recent session context and retry cancellation boundaries."""


def suppress_duplicate(handler, *, suppress, **dependencies):
    return suppress(handler, **dependencies)


def load_recent_context(*, load, **dependencies):
    return load(**dependencies)


def cancel_retry(*, cancel_pending, **dependencies):
    return cancel_pending(**dependencies)
