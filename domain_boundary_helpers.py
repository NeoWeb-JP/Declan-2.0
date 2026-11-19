"""Pure domain helpers shared by server compatibility boundaries."""

from execution_results import Outcome


def chained_outcome_result(routine, lighting):
    routine, lighting = Outcome(routine), Outcome(lighting)
    if routine in {Outcome.STARTED, Outcome.EXECUTION_COMPLETED, Outcome.REPORTED_SUCCESS} and lighting is Outcome.CONFIRMED:
        return routine
    if routine in {Outcome.REPORTED_SUCCESS, Outcome.EXECUTION_COMPLETED, Outcome.PARTIAL} or lighting in {Outcome.CONFIRMED, Outcome.PARTIAL}:
        return Outcome.PARTIAL
    if Outcome.UNVERIFIED in (routine, lighting):
        return Outcome.UNVERIFIED
    return routine if routine is lighting else Outcome.FAILED


def approved_area_labels(areas, *, room_key):
    """Expose readable HA area names without replacing them with legacy aliases."""
    labels = {}
    # read_ha_areas includes compatibility aliases (e.g. bedroom for
    # Master Bedroom). Prefer the full HA area name over its alias.
    for name in areas:
        key = room_key(name)
        if len(name) > len(labels.get(key, "")):
            labels[key] = name.title()
    labels["everywhere"] = "Everywhere"
    return labels


def bounded_ai_plan(message, exposed, settings, usage_sink=None, inventory=None, *, planner, credentials, money):
    plan = planner.request_plan(message, exposed, model=settings["model"], api_key=credentials.get_key(), usage_sink=usage_sink, inventory=inventory,
        max_cost_micro_usd=money(settings["request_ceiling_usd"], allow_zero=False))
    if len(plan) > settings["max_actions"]:
        raise ValueError("Too many proposed actions")
    return plan

