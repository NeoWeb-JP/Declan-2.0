"""Household questions answered straight from Home Assistant (#834 P2).

One place for the read-mostly household features, so the turn entry only asks
"is this a household question?" once:

- FUT-30 who's home (``declan.ha.presence``)
- FUT-31 car questions and charging (``declan.ha.car``)
- FUT-33 find my phone (``declan.ha.find_phone``)
- FUT-29 morning briefing (``declan.ha.briefing``)
- FUT-41 camera event questions from Frigate (``declan.ha.camera_events``)
- FUT-32 what each satellite can do (``declan.ha.satellites``)

Each feature module has ``match(phrase)`` and ``result(request, connection, ...)``.
``result`` returns None when the request turned out not to be for it (for
example "is the washing in?" isn't a person), so the rest of Declan answers.
"""
from declan.ha import briefing, camera_events, car, find_phone, ha_reads, presence, satellites

FEATURES = (("briefing", briefing), ("car", car), ("phone", find_phone), ("cameras", camera_events),
            ("satellites", satellites), ("presence", presence))


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
    if name in {"presence", "car", "briefing", "cameras"}:
        return module.result(payload, connection, guest=ha_reads.guest(services))
    if name == "satellites":
        return module.result(payload, connection, origin=origin)
    if name == "phone":
        return module.result(payload, connection)
    return None
