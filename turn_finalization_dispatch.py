"""Turn finalization boundaries.

Keep the session lock in the caller so context preparation, response
composition, and persistence remain one atomic turn transaction.
"""


def prepare_context(previous, *, prepare, action_results, light_result,
                    outcome, scope, message, now, suggestion_factory):
    return prepare(
        previous, action_results=action_results, light_result=light_result,
        outcome=outcome, scope=scope, message=message, now=now,
        suggestion_factory=suggestion_factory,
    )


def compose_response(message, session_id, routine_reply, *, compose_turn, **dependencies):
    return compose_turn(message, session_id, routine_reply, **dependencies)


def persist_response(response, *, persist, **dependencies):
    return persist(response, **dependencies)
