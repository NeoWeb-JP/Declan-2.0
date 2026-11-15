"""Orchestrate the guarded model-planning path, without implicit HA access.

The caller supplies the trusted inventory, a configured planner, an authorised
dispatcher, and a persistent budget database. No live server route invokes this
module until those dependencies and owner controls are connected.
"""
from action_executor import execute_verified, summarise
from action_plan import validate_plan
from ai_budget import reserve, settle
from ha_action_preflight import preflight


def run_guarded_fallback(
    utterance, inventory, *, planner, dispatcher, budget_db,
    monthly_limit_micro_usd, request_ceiling_micro_usd,
    charge_micro_usd=None, sensitive_confirmed=False,
):
    """Execute only a fully validated plan after reserving budget.

    The planner must return validated CandidateAction instances. The caller
    must provide a trusted, permission-aware dispatcher that verifies states.
    No execution occurs if budget, planning or preflight fails.

    charge_micro_usd is an optional, trusted actual-charge callback invoked
    only after the planner returns. If absent, the full reservation is retained.
    """
    if not isinstance(inventory, list):
        raise ValueError("Trusted HA inventory is required")
    if not callable(planner) or not callable(dispatcher):
        raise ValueError("Trusted planner and dispatcher are required")
    exposed = []
    for row in inventory:
        if not isinstance(row, dict) or not isinstance(row.get("entity_id"), str):
            raise ValueError("Invalid inventory")
        exposed.append(row["entity_id"])
    if len(set(exposed)) != len(exposed):
        raise ValueError("Duplicate HA entity")
    reservation = reserve(
        budget_db, limit_micro_usd=monthly_limit_micro_usd,
        max_request_micro_usd=request_ceiling_micro_usd,
    )
    # Fail closed: retain the full reservation on exceptions or uncertain costs.
    plan = planner(utterance, tuple(exposed))
    if not plan:
        return {"reply": "I couldn't safely identify an action. Please be more specific.",
                "outcome": "unresolved", "actions": ()}
    # Never trust a planner's claim that its candidates were validated.
    try:
        raw = {"actions": [{"entity_id": action.entity_id, "service": action.service,
                            "depends_on": list(action.depends_on)} for action in plan]}
    except (AttributeError, TypeError):
        raise ValueError("Planner returned invalid candidates") from None
    validated = validate_plan(raw, exposed)
    checked = preflight(validated, inventory, confirmed_sensitive=sensitive_confirmed)
    # Cost settlement is deliberately after planning, before side effects.
    # A missing actual-charge callback retains the full reserved ceiling.
    if charge_micro_usd is not None:
        actual = charge_micro_usd()
        settle(budget_db, reservation, actual)
    results = execute_verified(checked, dispatcher)
    reply, outcome = summarise(results)
    return {"reply": reply, "outcome": outcome, "actions": results}
