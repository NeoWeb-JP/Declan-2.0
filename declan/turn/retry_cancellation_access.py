"""Cancel a pending retry under the shared session lock."""


def cancel_pending_retry(
    *, message, session_id, scope, source, speaker, lock,
    converse, record, log_error, cancel,
):
    with lock:
        return cancel(
            message, session_id, scope=scope, source=source,
            speaker=speaker, converse=converse,
            record=record, log_error=log_error,
        )
