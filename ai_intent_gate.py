"""Bound unmatched input; let the guarded planner decide whether it is actionable.

Local handlers run first. Eligibility does not grant any device permissions or
enable general chat: an unsupported request must produce an empty action plan.
"""


def is_action_request(utterance):
    """Check input eligibility, not intent; retain the existing caller API."""
    return isinstance(utterance, str) and 0 < len(utterance) <= 1000 and bool(utterance.strip())
