"""Apply sensitive confirmation results to the active command phrase."""


def resolved_confirmation(confirmation, phrase, effective_message):
    """Return session, phrase, effective message and optional immediate reply."""
    if confirmation.confirmed:
        phrase = confirmation.phrase
        effective_message = confirmation.phrase
    return confirmation.session_id, phrase, effective_message, confirmation.reply


def resolve_confirmation(message, phrase, session_id, *, confirm, source,
                         satellite, origin_device, speaker, evaluate,
                         confirmation_response, normalize, guest_commands,
                         confirmations, record, diagnostic_id, log_error,
                         resolve, effective_message):
    confirmation = confirm(
        message, phrase, session_id, source=source, satellite=satellite,
        origin_device=origin_device, speaker=speaker, evaluate=evaluate,
        confirmation_response=confirmation_response, normalize=normalize,
        guest_commands=guest_commands, confirmations=confirmations,
        record=record, diagnostic_id=diagnostic_id, log_error=log_error,
    )
    return resolve(confirmation, phrase, effective_message)
