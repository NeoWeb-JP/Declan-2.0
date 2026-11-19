"""Routine turn selection, read-only preview, and script execution contracts."""
import re
from execution_results import ExecutionResult, Outcome
from routine_selection_results import RoutineSelection, RoutineSelectionKind, RoutineTurnSelection


def select_routine_turn_result(phrase, origin, *, select, parse_movie):
    for join in re.finditer(r"(?:,\s*|\s+)(?:and then|and|then) (?=turn |make |set |dim |play )", phrase):
        follow_on = phrase[join.end():]
        if follow_on.startswith("play ") and parse_movie(phrase[:join.start()].removeprefix("run ")):
            continue
        if routine := select(phrase[:join.start()], origin):
            return RoutineTurnSelection(RoutineSelection.coerce(routine), follow_on)
    routine = select(phrase, origin)
    return RoutineTurnSelection(RoutineSelection.coerce(routine)) if routine is not None else None


def preview_routine_result(phrase, origin=None, *, select_turn):
    """Read-only preview of a Home Assistant script; never dispatch actions."""
    selection = select_turn(phrase, origin)
    if not selection:
        return ExecutionResult("I couldn't find that script in Home Assistant. Nothing has been run.", Outcome.UNRESOLVED)
    selection = RoutineTurnSelection.coerce(selection)
    routine = selection.routine
    if selection.follow_on:
        return ExecutionResult("I cannot preview chained commands yet. Nothing has been run.", Outcome.UNRESOLVED)
    if routine.kind is RoutineSelectionKind.AMBIGUOUS:
        return ExecutionResult("Several Home Assistant scripts match. Nothing has been run.", Outcome.UNRESOLVED)
    if routine.kind is RoutineSelectionKind.HOUSE_STATUS_MISSING:
        return ExecutionResult("I couldn't find a House Status script in Home Assistant. Nothing has been run.", Outcome.NOT_CONFIGURED)
    if routine.kind is not RoutineSelectionKind.SCRIPT:
        return ExecutionResult("I couldn't identify a Home Assistant script. Nothing has been run.", Outcome.UNRESOLVED)
    script = routine.entity_id
    variables = ", ".join(f"{key}={value}" for key, value in routine.options.items())
    detail = f" with {variables}" if variables else ""
    return ExecutionResult(f"Preview: I would request Home Assistant script {script}{detail}. "
            "The script's internal actions and final reply cannot be predicted without running it. "
            "Simulated spoken response: Starting the routine. Nothing has been run.", Outcome.PREVIEW)


def execute_routine_result(selection, action_results, *, approved=False, discovery, connect):
    """Typed execution result for local routine selection with optional status."""
    selection = RoutineSelection.coerce(selection)
    options = selection.options
    if selection.kind is RoutineSelectionKind.SCRIPT:
        if options.get("_declan_background"):
            return discovery.enqueue_result(
                connect(), selection.entity_id,
                {key: value for key, value in options.items() if not key.startswith("_declan_")})
        return discovery.execute_result(
            connect(), {"entity_id": selection.entity_id},
            parameters={key: value for key, value in options.items() if not key.startswith("_declan_")},
            expect_response=options.get("_declan_expect_response", False),
            action_results=action_results)
    if selection.kind is RoutineSelectionKind.AMBIGUOUS:
        return ExecutionResult("Several Home Assistant scripts match that name. Please use a more specific name.", Outcome.UNRESOLVED), None
    if selection.kind is RoutineSelectionKind.HOUSE_STATUS_MISSING:
        return ExecutionResult("I could not find a House Status script in Home Assistant.", Outcome.NOT_CONFIGURED), None
    return ExecutionResult("I couldn't find that routine in Home Assistant.", Outcome.NOT_CONFIGURED), None
