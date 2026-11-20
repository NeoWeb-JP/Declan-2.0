"""Per-script defaults and rendering; shared storage is in response_library."""
import re
import sqlite3
from enum import StrEnum

from declan.core import history
from declan.turn import response_library
from declan.core.execution_results import Outcome, parse_outcome

ENTITY = re.compile(r"script\.[a-z0-9_]{1,200}\Z")
PHASES = response_library.PHASES
MODES = response_library.MODES
ACTIONS = response_library.ACTIONS
validate = response_library.validate
revision = response_library.revision
_table = response_library._table


class ResponsePhase(StrEnum):
    REQUESTED = "requested"
    COMPLETED = "completed"
    FAILURE = "failure"


def response_phase(outcome) -> ResponsePhase | None:
    outcome = parse_outcome(outcome)
    if outcome is Outcome.STARTED:
        return ResponsePhase.REQUESTED
    if outcome in {Outcome.CONFIRMED, Outcome.REPORTED_SUCCESS, Outcome.EXECUTION_COMPLETED}:
        return ResponsePhase.COMPLETED
    if outcome in {Outcome.FAILED, Outcome.PARTIAL, Outcome.UNVERIFIED,
                   Outcome.UNRESOLVED, Outcome.NOT_CONFIGURED, Outcome.CANCELLED}:
        return ResponsePhase.FAILURE
    return None


def defaults(item):
    from declan.turn import personality_policy as policy
    from declan.turn import personality
    from declan.ha import script_discovery
    profile: dict[str, dict[str, dict[str, list[str]]]] = {phase: {mode: {action: [] for action in ACTIONS} for mode in MODES} for phase in PHASES}
    aliases = script_discovery.phrases(item)
    category = next((name for name, aliases_for in (
        ("morning", {"good morning"}), ("night", {"good night"}),
        ("sexy", {"sexy time"}), ("movie", {"movie time", "start movie time", "end movie time"}),
        ("dinner", {"dinner", "dinner is served", "dinner time"}),
    ) if aliases & aliases_for), "general")
    for mode, guest in (("sass", False), ("guest", True)):
        generic = policy._GUEST if guest else policy._SAVAGE
        profile["completed"][mode]["default"] = list(generic)
        profile["requested"][mode]["default"] = ["I'll start the routine."]
        if category in {"morning", "night"}:
            prefix = "Good morning. " if category == "morning" else "Good night. "
            lines = getattr(policy, f"_{category.upper()}_{'GUEST' if guest else 'HOME'}")
            profile["requested"][mode]["default"] = [prefix + line for line in lines]
            profile["completed"][mode]["default"] = list(personality.LINES[f"good_{category}"][guest])
        elif category in {"movie", "sexy"}:
            table = getattr(policy, f"_{category.upper()}_{'GUEST' if guest else 'HOME'}")
            profile["requested"][mode]["default"] = []
            for action, lines in table.items():
                profile["requested"][mode][action] = list(lines)
                legacy = f"movie_{action}" if category == "movie" else f"sexy_time_{action}"
                profile["completed"][mode][action] = list(personality.LINES.get(legacy, (generic, generic))[guest])
        elif category == "dinner":
            lines = policy._DINNER_GUEST if guest else policy._DINNER_HOME
            profile["completed"][mode]["default"] = list(lines)
    return profile


def snapshot(item):
    return response_library.snapshot(item, defaults)


def save(item, profile, expected):
    return response_library.save(item, profile, expected, defaults)


def select(item, phase, guest, action="default"):
    return response_library.select(item, phase, guest, action, defaults=defaults)


def render(selection, outcome, original, *, guest=False):
    """Replace ordinary routine wording, retain diagnostics and informative scripts."""
    from declan.turn.routine_selection_results import RoutineSelection, RoutineSelectionKind
    selection = RoutineSelection.coerce(selection)
    if selection.kind is not RoutineSelectionKind.SCRIPT or not selection.entity_id:
        return original
    phase = response_phase(outcome)
    if phase is None:
        return original
    options = selection.options
    entity = selection.entity_id
    item = {"entity_id": entity, "name": entity[7:].replace('_', ' ')}
    # Rendering is not bound to a specific HA credential scope. Do not scan
    # another request's authenticated discovery cache for script metadata.
    # Saved response profiles remain keyed to the stable script entity ID.
    action = options.get("requested_action", options.get("operation", "default"))
    try:
        # Informational scripts retain their returned content until the user
        # explicitly saves response lists for them.
        if options.get("_declan_expect_response"):
            with history.database() as db:
                _table(db)
                saved = db.execute("SELECT 1 FROM routine_responses WHERE entity=?", (entity,)).fetchone()
            if not saved:
                return original
        line = select(item, phase.value, guest, action)
    except (OSError, ValueError, sqlite3.Error):
        return original
    if phase is ResponsePhase.FAILURE:
        return (line + " " if line else "") + original
    return line or ("Routine requested." if phase is ResponsePhase.REQUESTED else "Routine finished.")
