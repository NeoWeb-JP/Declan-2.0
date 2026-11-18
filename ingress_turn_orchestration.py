"""Ingress context, learned intent, retry, and confirmation orchestration.

Keep the caller's early-return decisions and lock boundaries unchanged.
"""


def resolve_origin(path, body, *, resolve):
    return resolve(path, body)


def resolve_learned_message(message, *, resolve, preprocess, normalize,
                            learned_intent, log_error):
    return resolve(
        message, preprocess=preprocess, normalize=normalize,
        learned_intent=learned_intent, log_error=log_error,
    )


def consume_retry(*, consume_context, session_id, scope, sessions, lock,
                  now, window_seconds, consume):
    return consume_context(
        session_id=session_id, scope=scope, sessions=sessions, lock=lock,
        now=now, window_seconds=window_seconds, consume=consume,
    )


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
