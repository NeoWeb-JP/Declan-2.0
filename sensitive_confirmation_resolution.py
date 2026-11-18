"""Apply sensitive confirmation results to the active command phrase."""


def resolved_confirmation(confirmation, phrase, effective_message):
    """Return session, phrase, effective message and optional immediate reply."""
    if confirmation.confirmed:
        phrase = confirmation.phrase
        effective_message = confirmation.phrase
    return confirmation.session_id, phrase, effective_message, confirmation.reply
