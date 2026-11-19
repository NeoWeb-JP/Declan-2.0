"""Strict validation boundary for OpenAI-proposed Home Assistant actions.

The model is not an authority: only exact exposed entity IDs and approved
service names may become candidate actions. This module performs no I/O.
"""
import re
from dataclasses import dataclass
from enum import StrEnum

ENTITY = re.compile(r"^(light|switch|fan|cover|script|media_player)\.[a-z0-9_]+$")
SERVICES = {
    "light": frozenset(("turn_on", "turn_off")),
    "switch": frozenset(("turn_on", "turn_off")),
    "fan": frozenset(("turn_on", "turn_off")),
    "cover": frozenset(("open_cover", "close_cover")),
    "script": frozenset(("turn_on",)),
    "media_player": frozenset(("media_stop", "media_pause", "media_play")),
}
MAX_ACTIONS = 8


@dataclass(frozen=True)
class CandidateAction:
    entity_id: str
    service: str
    depends_on: tuple[int, ...] = ()


def validate_plan(payload, exposed_entities):
    """Reject unsafe or ambiguous plans in full, before any action.

    exposed_entities is the server's trusted HA exposure set, not model input.
    Caller must additionally apply HA permissions, sensitive confirmation,
    and per-device capability checks before executing.
    """
    if not isinstance(payload, dict) or set(payload) != {"actions"}:
        raise ValueError("Invalid action plan")
    actions = payload["actions"]
    if not isinstance(actions, list) or not 1 <= len(actions) <= MAX_ACTIONS:
        raise ValueError("Invalid action count")
    exposed = frozenset(exposed_entities)
    result = []
    for index, item in enumerate(actions):
        if not isinstance(item, dict) or set(item) - {"entity_id", "service", "depends_on"}:
            raise ValueError("Unexpected action fields")
        entity = item.get("entity_id")
        service = item.get("service")
        deps = item.get("depends_on", [])
        if (not isinstance(entity, str) or not ENTITY.fullmatch(entity)
                or entity not in exposed or not isinstance(service, str)
                or service not in SERVICES[entity.split(".", 1)[0]]):
            raise ValueError("Action not permitted")
        if (not isinstance(deps, list) or len(set(map(str, deps))) != len(deps)
                or any(type(dep) is not int or dep < 0 or dep >= index for dep in deps)):
            raise ValueError("Invalid action dependencies")
        result.append(CandidateAction(entity, service, tuple(deps)))
    return tuple(result)


class ActionReadiness(StrEnum):
    PENDING = "pending"
    SKIPPED_DEPENDENCY = "skipped_dependency"


@dataclass(frozen=True)
class OrderedActionResult:
    index: int
    action: CandidateAction
    status: ActionReadiness

    def __post_init__(self):
        if type(self.index) is not int or self.index < 0:
            raise ValueError("Ordered action index must be a nonnegative integer")
        if not isinstance(self.action, CandidateAction):
            raise TypeError("Ordered action requires a candidate action")
        if not isinstance(self.status, ActionReadiness):
            raise TypeError("Ordered action status must be an ActionReadiness")

    def as_legacy_tuple(self):
        return self.index, self.action, self.status.value


def execution_order_result(plan, outcomes):
    """Yield pending candidates; skip dependencies that did not succeed.

    outcomes maps previous action indices to verified success booleans.
    Independent candidates are unaffected by a failed predecessor.
    """
    for index, action in enumerate(plan):
        if any(outcomes.get(dep) is not True for dep in action.depends_on):
            yield OrderedActionResult(index, action, ActionReadiness.SKIPPED_DEPENDENCY)
        else:
            yield OrderedActionResult(index, action, ActionReadiness.PENDING)


def execution_order(plan, outcomes):
    """Compatibility API retaining index/action/plain-status tuples."""
    for result in execution_order_result(plan, outcomes):
        yield result.as_legacy_tuple()
