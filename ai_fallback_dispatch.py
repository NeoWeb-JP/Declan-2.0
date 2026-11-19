"""Permission-bounded OpenAI fallback dispatch."""
import re
import sqlite3
import logging
from execution_results import ExecutionResult, Outcome
from ai_budget import BudgetExhausted, MICRO_USD
from model_response_results import IncompletePlanningError, PlanningTimeoutError
from ai_context import ContextSelectionError
from ha_action_preflight import SensitiveCoverConfirmationRequired
from ai_pricing import model_profile, require_available, RetiredModelError

LOGGER = logging.getLogger(__name__)


def guarded_openai_fallback_result(message, *, source, exposed_entities=(), settings_reader, intent_gate, connect, inventory_reader, inventory_module, context_selector, planner_module, settings_module, history_module, fallback_runner, dispatcher, pricing, bounded_plan, evidence_factory, response_factory, location_reader=None):
    """Opt-in fallback after local handlers; sensitive cover plans are refused."""
    try:
        settings = settings_reader()
    except (OSError, ValueError, sqlite3.Error):
        return response_factory(ExecutionResult("AI settings are unavailable; local commands still work.", Outcome.UNRESOLVED))
    if not settings["enabled"] or not intent_gate(message):
        return None
    try:
        profile = model_profile(settings['model'], settings.get('model_config'))
        require_available(profile)
    except RetiredModelError:
        return response_factory(ExecutionResult(
            "The configured AI model is retired. Update AI settings; local commands still work.", Outcome.UNRESOLVED))
    except ValueError:
        return response_factory(ExecutionResult("AI model pricing or capabilities are unavailable. Update AI settings.", Outcome.UNRESOLVED))
    settings = {**settings, 'model_config': profile}
    connection = connect()
    if connection is None:
        return response_factory(ExecutionResult("Home Assistant is unavailable.", Outcome.UNAVAILABLE))
    inventory_result = inventory_module.InventoryResult.coerce(inventory_reader(connection))
    inventory, error = inventory_result.inventory, inventory_result.error
    if error or inventory is None:
        return response_factory(ExecutionResult("I couldn't verify Home Assistant devices.", Outcome.UNAVAILABLE))
    # Only the authenticated HA integration supplies its effective Assist
    # exposure set. Never use all inventory rows as implicit permission.
    if not isinstance(exposed_entities, (list, tuple)) or len(exposed_entities) > 20000:
        return response_factory(ExecutionResult("AI device permissions are unavailable.", Outcome.UNRESOLVED))
    if not exposed_entities or any(
            not isinstance(item, str) or not re.fullmatch(r"[a-z_]+\.[a-z0-9_]+", item)
            for item in exposed_entities):
        return response_factory(ExecutionResult("AI device permissions are unavailable.", Outcome.UNRESOLVED))
    permitted = set(exposed_entities)
    if len(permitted) != len(exposed_entities):
        return response_factory(ExecutionResult("AI device permissions are unavailable.", Outcome.UNRESOLVED))
    safe = [row for row in inventory if row["entity_id"] in permitted
            and row["entity_id"].split(".", 1)[0] in settings["allowed_domains"]]
    try:
        if len(safe) > planner_module.MAX_CONTEXT:
            locations = location_reader(connection) if location_reader is not None else None
            safe = context_selector(safe, message, limit=planner_module.MAX_CONTEXT,
                                    locations=locations, max_actions=settings['max_actions'])
        else:
            safe = context_selector(safe, message, limit=planner_module.MAX_CONTEXT)
        if not safe:
            return response_factory(ExecutionResult(
                "No permitted devices are available for AI planning.", Outcome.UNRESOLVED))
        limit = settings_module._money(settings["monthly_budget_usd"], allow_zero=True)
        ceiling = settings_module._money(settings["request_ceiling_usd"], allow_zero=False)
        usage = {}
        with history_module.database() as db:
            result = fallback_runner(
                message, safe,
                planner=lambda text, exposed: bounded_plan(
                    text, exposed, settings, usage_sink=lambda value: usage.update({"value": value}),
                    inventory=safe),
                dispatcher=lambda action: dispatcher(
                    action, connection,
                    authorised=lambda candidate: candidate.entity_id in {
                        row["entity_id"] for row in safe
                        if row["state"] not in ("unknown", "unavailable")
                    }),
                budget_db=db, monthly_limit_micro_usd=limit,
                request_ceiling_micro_usd=ceiling,
                charge_micro_usd=lambda: pricing(settings["model"], usage.get("value"), profile=settings.get('model_config')),
            )
        return response_factory(result, tuple(
            evidence_factory.from_action(action, include_detail=settings["diagnostics"])
            for action in result.actions
        ))
    except ContextSelectionError as error:
        return response_factory(ExecutionResult(str(error), Outcome.UNRESOLVED))
    except SensitiveCoverConfirmationRequired:
        return response_factory(ExecutionResult(
            "AI can't operate garage or gate covers. Use Home Assistant directly. No devices were changed.",
            Outcome.UNRESOLVED))
    except PlanningTimeoutError:
        LOGGER.warning("OpenAI planning timed out; no device actions dispatched")
        return response_factory(ExecutionResult(
            "OpenAI took too long to plan. No devices were changed. Local commands still work.",
            Outcome.UNRESOLVED))
    except IncompletePlanningError as error:
        reply = ("OpenAI reached its planning token limit. No devices were changed; please try a shorter request."
                 if error.reason == "max_output_tokens" else
                 "OpenAI couldn't finish planning. No devices were changed.")
        return response_factory(ExecutionResult(reply, Outcome.UNRESOLVED))
    except BudgetExhausted as error:
        remaining = error.remaining_micro_usd / MICRO_USD
        return response_factory(ExecutionResult(
            f'Monthly OpenAI budget exhausted for this request. ${remaining:.2f} remains; local commands still work.',
            Outcome.UNRESOLVED))
    except (ValueError, OSError, sqlite3.Error):
        return response_factory(ExecutionResult("I couldn't safely complete that request using OpenAI.", Outcome.UNRESOLVED))
