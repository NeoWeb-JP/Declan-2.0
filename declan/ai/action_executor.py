"""Execute already-authorised plans; typed results never confuse receipt with success."""
from declan.ai.action_plan import CandidateAction, ActionReadiness, execution_order_result
# Re-export ActionResult for existing Python callers.
from execution_results import ActionResult, ActionStatus, DispatchResult, ExecutionResult, Outcome
import logging

LOGGER = logging.getLogger(__name__)


def execute_verified(plan, dispatcher):
    """Run in order, skip failed dependencies, continue independent steps.

    New dispatchers return DispatchResult. Existing (status, detail) dispatchers
    are converted and validated at the boundary. HTTP 200 alone is not success.
    """
    if not isinstance(plan, tuple) or not all(isinstance(x, CandidateAction) for x in plan):
        raise ValueError("Plan has not been validated")
    if not callable(dispatcher):
        raise ValueError("Trusted dispatcher is required")
    results = []
    outcomes: dict[int, bool] = {}
    for decision in execution_order_result(plan, outcomes):
        index, action = decision.index, decision.action
        if decision.status is ActionReadiness.SKIPPED_DEPENDENCY:
            results.append(ActionResult(index, action.entity_id, action.service,
                                        ActionStatus.SKIPPED_DEPENDENCY))
            outcomes[index] = False
            continue
        try:
            dispatch = DispatchResult.coerce(dispatcher(action))
        except Exception as error:
            # Never expose provider exceptions or their secrets in voice/history.
            # Log only the type so a programming error is not silent.
            LOGGER.warning("Action dispatch failed for %s.%s (%s)", action.entity_id, action.service, type(error).__name__)
            dispatch = DispatchResult(ActionStatus.FAILED, "Dispatch or verification failed")
        results.append(ActionResult(index, action.entity_id, action.service,
                                    dispatch.status, dispatch.detail[:240]))
        outcomes[index] = results[-1].confirmed
    return tuple(results)


def summarise_result(results):
    """Return an immutable typed summary with the original action evidence."""
    results = tuple(results)
    if any(not isinstance(result, ActionResult) for result in results):
        raise ValueError("Action results are required")
    counts = {status: sum(result.status is status for result in results) for status in ActionStatus}
    if not results:
        return ExecutionResult("No actions were performed.", Outcome.UNRESOLVED)
    if counts[ActionStatus.CONFIRMED] == len(results):
        return ExecutionResult("All requested actions were confirmed.", Outcome.CONFIRMED, results)
    if counts[ActionStatus.CONFIRMED]:
        return ExecutionResult(
            f"{counts[ActionStatus.CONFIRMED]} confirmed, {counts[ActionStatus.FAILED]} failed, "
            f"{counts[ActionStatus.UNVERIFIED]} unverified and {counts[ActionStatus.SKIPPED_DEPENDENCY]} skipped.",
            Outcome.PARTIAL, results)
    return ExecutionResult(
        f"No actions confirmed: {counts[ActionStatus.FAILED]} failed, "
        f"{counts[ActionStatus.UNVERIFIED]} unverified and {counts[ActionStatus.SKIPPED_DEPENDENCY]} skipped.",
        Outcome.UNVERIFIED, results)


def summarise(results):
    """Compatibility API: retain the existing (reply, outcome-string) tuple."""
    return summarise_result(results).as_legacy_pair()
