"""Opt-in typed accumulation with compatibility for existing list callers."""
from action_evidence_wire import TYPED_EVIDENCE
from movie_action_evidence import MovieActionEvidence


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
