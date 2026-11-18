"""Atomic turn context preparation, composition and persistence."""
def finalize(session_id, action_results, light_result, outcome, scope, message, effective_message, routine_reply, lighting_context, response_guest_mode, routine_turn, phrase, guest_mode, visitor_present, routine_voice_result, routine_status, status_target, information_context, pending_retry, source, body, *,
             sessions, session_lock, clock, turn_context_preparation, turn_finalization, turn_response_composition, turn_response_orchestration, personality_policy, personality_lines, music, routine_responses, lighting_intents, parse_light_command, command_responses, response_composition, turn_persistence_orchestration, unmatched_reply, retry_learning, history, diagnostics, session_turn_state, retry_training_persistence, conversation_persistence, log_error, converse):
    with session_lock:
        previous = sessions.get(session_id)
        actions, phrase_suggestion = turn_context_preparation.prepare_turn_context(
            previous, action_results=action_results, light_result=light_result,
            outcome=outcome, scope=scope, message=message, now=clock(),
            suggestion_factory=turn_finalization.lighting_phrase_suggestion,
        )
        response = turn_response_composition.compose_turn_result(
            effective_message, session_id, routine_reply,
            lighting_context=lighting_context, scope=scope,
            response_guest_mode=response_guest_mode, outcome=outcome,
            routine_turn=routine_turn, light_result=light_result,
            phrase=phrase, action_results=action_results,
            guest_mode=guest_mode, visitor_present=visitor_present,
            routine_voice_result=routine_voice_result, routine_status=routine_status,
            converse=converse, compose=turn_response_orchestration.compose,
            apply_outcome_metadata=turn_finalization.apply_outcome_metadata,
            personality=personality_policy, lines=personality_lines,
            parse_music=music.parse, parse_music_control=music.parse_control,
            render_routine=routine_responses.render,
            response_category=lighting_intents.response_category,
            parse_light_command=parse_light_command,
            render_failure=command_responses.failure,
            composition=response_composition,
        )
        response = turn_persistence_orchestration.persist_turn_result(
            response, sessions=sessions,
            apply_outcome_metadata=turn_finalization.apply_outcome_metadata,
            finalize=turn_persistence_orchestration.finalize_turn,
            message=message, phrase=phrase,
            outcome=outcome, scope=scope, status_target=status_target,
            information_context=information_context,
            light_result=light_result, action_results=action_results,
            actions=actions, unmatched_reply=unmatched_reply,
            now=clock(), pending_retry=pending_retry,
            effective_message=effective_message,
            similar=retry_learning.similar,
            normalize_phrase=history.normalize_phrase,
            teach_phrase=history.teach_phrase, source=source,
            routine_status=routine_status,
            phrase_suggestion=phrase_suggestion,
            speaker=body.get("speaker"), record=history.record,
            diagnostic_id=diagnostics.current_id,
            log_error=log_error, state_module=session_turn_state,
            training_module=retry_training_persistence,
            history_module=conversation_persistence,
        )
    return response
