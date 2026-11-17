"""Handle sensitive-action confirmation response before normal dispatch."""
from confirmation_results import ConfirmationDecision, ConfirmationDecisionResult, ConfirmationTurnResult


def confirmation_turn_result(message, phrase, session_id, *, source, satellite,
                             origin_device, speaker, evaluate, confirmation_response,
                             normalize, guest_commands, confirmations, record,
                             diagnostic_id, log_error):
    """Retain typed confirmation decisions through the execution gate."""
    if source != "assist":
        return ConfirmationTurnResult(session_id, phrase, None, False)
    decision = evaluate(
        message, phrase, session_id, satellite=satellite,
        origin_device=origin_device, speaker=speaker,
        normalize=normalize, guest_commands=guest_commands,
        confirmations=confirmations,
    )
    if not isinstance(decision, ConfirmationDecisionResult):
        raise ValueError("Confirmation evaluator must return a typed decision")
    reply = confirmation_response(
        decision.evaluation.decision, decision.session_id, source=source,
        message=message, speaker=speaker, record=record,
        diagnostic_id=diagnostic_id, log_error=log_error,
    )
    confirmed = decision.evaluation.decision is ConfirmationDecision.CONFIRMED and reply is None
    return ConfirmationTurnResult(decision.session_id,
                                  decision.evaluation.approved_phrase if confirmed else phrase,
                                  reply, confirmed)


def confirmation_turn(message, phrase, session_id, *, source, satellite,
                      origin_device, speaker, evaluate, confirmation_response,
                      normalize, guest_commands, confirmations, record,
                      diagnostic_id, log_error):
    """Return (session_id, approved_phrase, reply, confirmed) for Assist requests.

    Non-Assist requests bypass confirmation and retain their original phrase.
    A non-None reply means the caller must return it before side effects.
    """
    if source != "assist":
        return session_id, phrase, None, False
    session_id, decision, approved_phrase = evaluate(
        message, phrase, session_id, satellite=satellite,
        origin_device=origin_device, speaker=speaker,
        normalize=normalize, guest_commands=guest_commands,
        confirmations=confirmations,
    )
    reply = confirmation_response(
        decision, session_id, source=source, message=message,
        speaker=speaker, record=record,
        diagnostic_id=diagnostic_id, log_error=log_error,
    )
    return session_id, approved_phrase if decision == "confirmed" and reply is None else phrase, reply, decision == "confirmed" and reply is None
