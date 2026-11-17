"""Prepare action and lighting follow-up context before response composition."""


def prepare_turn_context(previous, *, action_results, light_result, outcome,
                         scope, message, now, suggestion_factory):
    """Return action names and the existing lighting phrase suggestion."""
    actions = {step["action"] for step in action_results if "action" in step}
    phrase_suggestion = suggestion_factory(
        previous, light_result=light_result, outcome=outcome,
        actions=actions, scope=scope, message=message, now=now,
    )
    return actions, phrase_suggestion
