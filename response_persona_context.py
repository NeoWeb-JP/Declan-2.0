"""Resolve response persona inputs independently of guest authority."""


def resolve_response_persona(read_guest_mode, read_visitors_present, personality_policy):
    """Return guest authority, visitor presence and the response persona mode."""
    guest_mode = read_guest_mode()
    visitor_present = read_visitors_present()
    # Presence affects the persona, never Guest Mode authority.
    # An explicit Guest Mode must remain polite even when visitor presence is off.
    # Unknown visitor state also fails closed for privacy.
    response_guest_mode = personality_policy.response_guest_mode(guest_mode, visitor_present)
    return guest_mode, visitor_present, response_guest_mode
