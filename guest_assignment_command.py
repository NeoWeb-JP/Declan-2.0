"""Parse guest assignment commands without performing Home Assistant actions."""
import re

_GUEST_ASSIGNMENT = re.compile(
    r"(?:we are going out and |we're going out and |set |make |put )?"
    r"([a-z][a-z '\-]{0,119}?) (?:are|is) in charge"
    r"(?: of the house)?"
)


def assignment_action(phrase, guest_commands):
    """Return a configured guest action or a named assignment, otherwise None."""
    if phrase in guest_commands:
        return guest_commands[phrase]
    match = _GUEST_ASSIGNMENT.fullmatch(phrase)
    return "assign:" + match[1].strip() if match else None
