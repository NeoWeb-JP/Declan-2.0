"""Typed discovered-script evidence with the existing provider projection."""
from dataclasses import dataclass
from routine_action_evidence import RoutineActionEvidence, RoutineActionStatus, parse_routine_actions


SCRIPT_ACTION_STATUSES = frozenset(status for status in RoutineActionStatus
                                   if status is not RoutineActionStatus.PLANNED)
COMPLETED_STATUSES = frozenset({RoutineActionStatus.CONFIRMED, RoutineActionStatus.ALREADY_SET})


@dataclass(frozen=True)
class ScriptActionEvidence:
    steps: tuple[RoutineActionEvidence, ...]
    required_steps_completed: bool

    def __post_init__(self):
        if not isinstance(self.steps, tuple) or any(
                not isinstance(step, RoutineActionEvidence) or step.status not in SCRIPT_ACTION_STATUSES
                for step in self.steps):
            raise ValueError("Script evidence requires supported typed action steps")
        if type(self.required_steps_completed) is not bool:
            raise ValueError("Script completion evidence must be a boolean")


def _status(step):
    try:
        return RoutineActionStatus(step.get("status"))
    except (ValueError, TypeError):
        return None


def parse_script_actions(steps):
    """Validate completion independently of the bounded diagnostic projection."""
    if not isinstance(steps, list):
        return ScriptActionEvidence((), True)
    completed = all(_status(step) in COMPLETED_STATUSES for step in steps
                    if isinstance(step, dict) and step.get("required", True))
    projected = []
    for step in steps[:200]:
        if not isinstance(step, dict) or _status(step) not in SCRIPT_ACTION_STATUSES:
            continue
        projected.append({key: step[key] for key in (
            "target", "status", "action", "entity_id", "required") if key in step})
    return ScriptActionEvidence(parse_routine_actions(projected), completed)
