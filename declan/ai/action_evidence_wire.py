"""Explicit serialization boundary for typed and existing legacy action rows."""
from execution_results import ActionResult
from declan.ha.lighting_action_evidence import LightingActionEvidence
from declan.ha.movie_action_evidence import MovieActionEvidence
from routine_action_evidence import RoutineActionEvidence
from declan.ai.fallback_action_evidence import FallbackActionEvidence


TYPED_EVIDENCE = (ActionResult, LightingActionEvidence, MovieActionEvidence, RoutineActionEvidence, FallbackActionEvidence)


def action_evidence_to_wire(rows):
    """Serialize recognized typed evidence without rewriting legacy JSON values."""
    if not isinstance(rows, (list, tuple)) or not any(isinstance(row, TYPED_EVIDENCE) for row in rows):
        return rows
    return [row.to_wire() if isinstance(row, TYPED_EVIDENCE) else row for row in rows]
