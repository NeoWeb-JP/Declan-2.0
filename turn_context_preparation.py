"""Prepare action and lighting follow-up context before response composition."""
from action_evidence_buffer import evidence_has_field, evidence_value


def prepare_turn_context(previous, *, action_results, light_result, outcome,
                         scope, message, now, suggestion_factory):
    """Return action names and the existing lighting phrase suggestion."""
    actions = {evidence_value(step, "action") for step in action_results if evidence_has_field(step, "action")}
    phrase_suggestion = suggestion_factory(
        previous, light_result=light_result, outcome=outcome,
        actions=actions, scope=scope, message=message, now=now,
    )
    return actions, phrase_suggestion
