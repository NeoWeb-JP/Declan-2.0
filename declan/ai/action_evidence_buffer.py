"""Opt-in typed accumulation with compatibility for existing list callers."""
from declan.ai.action_evidence_wire import TYPED_EVIDENCE
from declan.ha.movie_action_evidence import MovieActionEvidence
from enum import StrEnum
from execution_results import ActionResult, ActionStatus
from declan.ai.fallback_action_evidence import FallbackActionEvidence
from declan.ha.lighting_action_evidence import LightingActionEvidence, parse_lighting_reason
from declan.turn.routine_action_evidence import RoutineActionEvidence


class LegacyCompletionStatus(StrEnum):
    CONFIRMED = "confirmed"
    ALREADY_SET = "already_set"
    COMPLETED = "completed"


def evidence_completed(row):
    """Interpret completion without projecting typed provider evidence to strings."""
    if isinstance(row, (LightingActionEvidence, RoutineActionEvidence)):
        return row.completed
    if isinstance(row, ActionResult):
        return row.confirmed
    if isinstance(row, FallbackActionEvidence):
        return row.status is ActionStatus.CONFIRMED
    if isinstance(row, dict):
        value = row.get("status")
        if isinstance(value, str):
            try:
                LegacyCompletionStatus(value)
                return True
            except ValueError:
                pass
    # A movie launch receipt confirms acceptance, never completion.
    return False


class ActionEvidenceBuffer(list):
    """Retain typed rows until explicit response/history serialization."""


def append_action_evidence(sink, evidence):
    if not isinstance(evidence, TYPED_EVIDENCE):
        raise ValueError("Action evidence producer requires a recognized typed row")
    sink.append(evidence if isinstance(sink, ActionEvidenceBuffer) else evidence.to_wire())


def extend_action_evidence(sink, evidence):
    for row in evidence:
        if isinstance(row, TYPED_EVIDENCE):
            append_action_evidence(sink, row)
        else:
            sink.append(row)


def evidence_value(row, name, default=None):
    """Read typed evidence fields without projecting or stringifying statuses."""
    if isinstance(row, dict):
        return row.get(name, default)
    if not isinstance(row, TYPED_EVIDENCE):
        return default
    if isinstance(row, MovieActionEvidence) and name == "action":
        return "open_app"
    value = getattr(row, name, None)
    return default if value is None else value


def evidence_has_field(row, name):
    if isinstance(row, dict):
        return name in row
    return evidence_value(row, name) is not None


def evidence_lighting_reason(row):
    """Retain typed lighting reasons and interpret legacy details at the boundary."""
    if isinstance(row, LightingActionEvidence):
        return row.reason
    return parse_lighting_reason(evidence_value(row, "detail"))
