"""Orchestrate the guarded model-planning path, without implicit HA access.

The caller supplies the trusted inventory, a configured planner, an authorised
dispatcher, and a persistent budget database. The live fallback route supplies
these dependencies after its owner controls and exposure checks.
"""
from declan.ai.action_executor import execute_verified, summarise_result
from declan.core.execution_results import ExecutionResult, Outcome
from declan.ai.action_plan import validate_plan
from declan.ai.ai_budget import reserve, settle
from declan.ha.ha_action_preflight import preflight
import logging
from declan.ai.model_response_results import NonBillablePlanningError

LOGGER = logging.getLogger(__name__)


def run_guarded_result(
    utterance, inventory, *, planner, dispatcher, budget_db,
    monthly_limit_micro_usd, request_ceiling_micro_usd,
    charge_micro_usd=None, sensitive_confirmed=False,
):
    """Execute only a fully validated plan after reserving budget.

    The planner must return validated CandidateAction instances. The caller
    must provide a trusted, permission-aware dispatcher that verifies states.
    No execution occurs if budget, planning or preflight fails.

    charge_micro_usd is an optional, trusted actual-charge callback invoked
    after planning, including failed responses with known usage. Proven unsent
    or rejected requests release their reservation; unknown costs retain it.
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
    try:
        plan = planner(utterance, tuple(exposed))
    except NonBillablePlanningError:
        settle(budget_db, reservation, 0)
        raise
    except Exception:
        if charge_micro_usd is not None:
            try:
                settle(budget_db, reservation, charge_micro_usd())
            except Exception as accounting_error:
                LOGGER.warning('Failed planning cost is unknown; reservation retained (reason=%s)',
                               type(accounting_error).__name__)
        raise
    # Charge even clarification-only responses. Missing usage retains the
    # full reservation, so a failed API accounting response cannot overspend.
    if charge_micro_usd is not None:
        actual = charge_micro_usd()
        settle(budget_db, reservation, actual)
    if not plan:
        return ExecutionResult("I couldn't safely identify an action. Please be more specific.",
                               Outcome.UNRESOLVED)
    # Never trust a planner's claim that its candidates were validated.
    try:
        raw = {"actions": [{"entity_id": action.entity_id, "service": action.service,
                            "depends_on": list(action.depends_on)} for action in plan]}
    except (AttributeError, TypeError):
        raise ValueError("Planner returned invalid candidates") from None
    validated = validate_plan(raw, exposed)
    checked = preflight(validated, inventory, confirmed_sensitive=sensitive_confirmed)
    results = execute_verified(checked, dispatcher)
    return summarise_result(results)


def run_guarded_fallback(
    utterance, inventory, *, planner, dispatcher, budget_db,
    monthly_limit_micro_usd, request_ceiling_micro_usd,
    charge_micro_usd=None, sensitive_confirmed=False,
):
    """Compatibility API for callers using the original Python mapping."""
    return run_guarded_result(
        utterance, inventory, planner=planner, dispatcher=dispatcher, budget_db=budget_db,
        monthly_limit_micro_usd=monthly_limit_micro_usd,
        request_ceiling_micro_usd=request_ceiling_micro_usd,
        charge_micro_usd=charge_micro_usd, sensitive_confirmed=sensitive_confirmed,
    ).as_legacy_mapping()
