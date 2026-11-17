"""Dispatch a matched roast with the configured guest response policy."""


def respond_to_roast(target, *, guest_mode, visitors_present, response_guest_mode, respond):
    """Return the existing (reply, outcome) pair for a matched roast target."""
    mode = response_guest_mode(guest_mode(), visitors_present())
    return respond(target, guest=mode != "off"), "confirmed"
