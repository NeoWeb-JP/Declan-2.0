"""Household questions answered straight from Home Assistant (#834 P2).

One place for the read-mostly household features, so the turn entry only asks
"is this a household question?" once:

- FUT-30 who's home (``declan.ha.presence``)
- FUT-31 car questions and charging (``declan.ha.car``)

Each feature module has ``match(phrase)`` and ``result(request, connection, ...)``.
``result`` returns None when the request turned out not to be for it (for
example "is the washing in?" isn't a person), so the rest of Declan answers.
"""
from declan.ha import car, ha_reads, presence

FEATURES = (("car", car), ("presence", presence))


def match(phrase):
    """(feature name, request) for the first feature that recognises the phrase, or None."""
    for name, module in FEATURES:
        request = module.match(phrase)
        if request is not None:
            return name, request
    return None


def result(request, services, *, origin=None):
    """An ExecutionResult, or None to let the rest of Declan answer."""
    name, payload = request
    module = dict(FEATURES)[name]
    try:
        connection = services.ha_device_connection()
    except (OSError, ValueError, TypeError, AttributeError):
        connection = None
    if name in {"presence", "car"}:
        return module.result(payload, connection, guest=ha_reads.guest(services))
    return None
