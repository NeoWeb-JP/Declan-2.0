"""Typed turn persistence and ordered session, training, history writes."""
from dataclasses import replace
from declan.turn.turn_response import TurnResponse


def persist_turn_result(response, *, apply_outcome_metadata, **dependencies):
    """Use the typed response as the authoritative outcome for persistence."""
    if not isinstance(response, TurnResponse):
        raise ValueError("Turn persistence requires a typed turn response")
    reply = response.to_wire(apply_outcome_metadata)
    dependencies["outcome"] = response.outcome
    dependencies["routine_status"] = response.routine_status
    persist_turn(reply, **dependencies)
    return replace(response, session_response=reply)


def persist_turn(reply, *, sessions, finalize, message, phrase, outcome,
                 scope, status_target, information_context, light_result,
                 action_results, actions, unmatched_reply, now, pending_retry,
                 effective_message, similar, normalize_phrase, teach_phrase,
                 source, routine_status, phrase_suggestion, speaker, record,
                 diagnostic_id, log_error, state_module, training_module,
                 history_module):
    """Look up the finalized reply session and forward persistence dependencies."""
    session = sessions[reply["session_id"]]
    return finalize(
        reply, session=session, message=message, phrase=phrase,
        outcome=outcome, scope=scope, status_target=status_target,
        information_context=information_context,
        light_result=light_result, action_results=action_results,
        actions=actions, unmatched_reply=unmatched_reply,
        now=now, pending_retry=pending_retry,
        effective_message=effective_message,
        similar=similar, normalize_phrase=normalize_phrase,
        teach_phrase=teach_phrase, source=source,
        routine_status=routine_status,
        phrase_suggestion=phrase_suggestion,
        speaker=speaker, record=record,
        diagnostic_id=diagnostic_id, log_error=log_error,
        state_module=state_module, training_module=training_module,
        history_module=history_module,
    )


def finalize_turn(reply, *, session, message, phrase, outcome, scope,
                  status_target, information_context, light_result,
                  action_results, actions, unmatched_reply, now,
                  pending_retry, effective_message, similar,
                  normalize_phrase, teach_phrase, source, routine_status,
                  phrase_suggestion, speaker, record, diagnostic_id,
                  log_error, state_module, training_module, history_module):
    """Maintain the established state -> training -> history write order."""
    retry_succeeded = state_module.update_turn(
        session, reply, message=message, phrase=phrase, outcome=outcome,
        scope=scope, status_target=status_target,
        information_context=information_context, light_result=light_result,
        action_results=action_results, actions=actions,
        unmatched_reply=unmatched_reply, now=now,
    )
    training_module.save_retry_training(
        reply, pending_retry=pending_retry,
        retry_succeeded=retry_succeeded, message=message,
        effective_message=effective_message, similar=similar,
        normalize_phrase=normalize_phrase, teach_phrase=teach_phrase,
        log_error=log_error,
    )
    history_module.save_turn(
        reply, source=source, message=message, outcome=outcome,
        routine_status=routine_status, action_results=action_results,
        phrase_suggestion=phrase_suggestion, speaker=speaker,
        record=record, diagnostic_id=diagnostic_id, log_error=log_error,
    )
