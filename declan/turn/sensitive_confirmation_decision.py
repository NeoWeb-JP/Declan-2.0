"""Evaluate voice-only sensitive action confirmation with origin binding."""
import secrets
from declan.turn import sensitive_confirmations
from declan.turn.confirmation_results import ConfirmationDecisionResult


def evaluate_result(message, phrase, session_id, *, satellite, origin_device, speaker,
                    normalize, guest_commands, confirmations, new_session_id=None):
    """Evaluate the typed confirmation provider without a legacy round trip."""
    spoken = normalize(message)
    candidate = spoken if spoken in sensitive_confirmations.YES | sensitive_confirmations.NO else phrase
    group = sensitive_confirmations.sensitive_group(candidate, None, guest_commands, {}, set())
    if not session_id:
        session_id = (new_session_id or (lambda: secrets.token_urlsafe(24)))()
    evaluation = confirmations.evaluate_result(
        session=session_id, origin=satellite or origin_device,
        phrase=candidate, group=group, speaker=speaker)
    return ConfirmationDecisionResult(session_id, evaluation)


def evaluate(message, phrase, session_id, *, satellite, origin_device, speaker,
             normalize, guest_commands, confirmations, new_session_id=None):
    """Return (session_id, decision, approved_phrase) for a spoken Assist turn."""
    spoken = normalize(message)
    candidate = spoken if spoken in sensitive_confirmations.YES | sensitive_confirmations.NO else phrase
    group = sensitive_confirmations.sensitive_group(
        candidate, None, guest_commands, {}, set())
    if not session_id:
        session_id = (new_session_id or (lambda: secrets.token_urlsafe(24)))()
    decision, approved_phrase = confirmations.evaluate(
        session=session_id, origin=satellite or origin_device,
        phrase=candidate, group=group, speaker=speaker)
    return session_id, decision, approved_phrase
