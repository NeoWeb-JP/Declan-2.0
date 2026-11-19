"""Privacy-safe aggregate operational metrics from bounded Declan diagnostic traces."""

from collections import defaultdict
from datetime import datetime, timezone
import json
import re
import sqlite3
from contextlib import closing
from time import time
from typing import TypedDict


class MetricSamples(TypedDict):
    durations: list[int | float]
    errors: int
    count: int

# Never use an arbitrary stored URL, speaker identifier or payload as a metric label.
ROUTES = frozenset({"/api/chat", "/api/assist", "/api/stt", "/api/tts",
                    "/api/assist/history"})
STAGE_NAME = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
FAILURE_OUTCOMES = frozenset({"failed", "unverified", "unavailable",
                              "not_configured", "partial", "error"})


def _quantile(values, percentile):
    if not values:
        return None
    ordered = sorted(values)
    position = ((len(ordered) - 1) * percentile + 99) // 100
    return ordered[position]


def _duration(value):
    return value if type(value) in (int, float) and 0 <= value <= 600_000 else None


def aggregate(traces, *, sampled_at=None):
    """Summarise bounded, redacted traces; emit no raw messages or trace IDs."""
    grouped: defaultdict[str, MetricSamples] = defaultdict(lambda: {"durations": [], "errors": 0, "count": 0})
    stages: defaultdict[str, MetricSamples] = defaultdict(lambda: {"durations": [], "errors": 0, "count": 0})
    for trace in traces:
        if not isinstance(trace, dict):
            continue
        route = trace.get("route")
        if not isinstance(route, str) or route not in ROUTES:
            continue
        row = grouped[route]
        row["count"] += 1
        outcome = trace.get("outcome")
        row["errors"] += int(isinstance(outcome, str) and outcome in FAILURE_OUTCOMES)
        duration = _duration(trace.get("duration_ms"))
        if duration is not None:
            row["durations"].append(duration)
        for stage in trace.get("stages", [])[:80] if isinstance(trace.get("stages"), list) else []:
            if not isinstance(stage, dict):
                continue
            name = stage.get("stage")
            if not isinstance(name, str) or STAGE_NAME.fullmatch(name) is None:
                continue
            item = stages[name]
            item["count"] += 1
            stage_outcome = stage.get("outcome")
            item["errors"] += int(isinstance(stage_outcome, str)
                                  and stage_outcome in FAILURE_OUTCOMES)
            stage_duration = _duration(stage.get("duration_ms"))
            if stage_duration is not None:
                item["durations"].append(stage_duration)

    def render(values):
        return {key: {"count": row["count"], "errors": row["errors"],
                      "p50_ms": _quantile(row["durations"], 50),
                      "p95_ms": _quantile(row["durations"], 95)}
                for key, row in sorted(values.items())}

    return {"sampled_at": datetime.fromtimestamp(sampled_at if sampled_at is not None else time(),
                                                 timezone.utc).isoformat(),
            "sample_limit": 500,
            "requests": render(grouped),
            "stages": render(stages)}


def summary(database, *, retention, now=None):
    """Read at most 500 recent traces, without exposing raw payloads."""
    current = time() if now is None else now
    if not database.exists():
        return aggregate([], sampled_at=current)
    with closing(sqlite3.connect(database, timeout=0.1)) as db:
        rows = db.execute("SELECT payload FROM traces WHERE created_at >= ? "
                          "ORDER BY created_at DESC LIMIT 500",
                          (current - min(retention, 86400),)).fetchall()
    traces = []
    for (payload,) in rows:
        try:
            traces.append(json.loads(payload))
        except (ValueError, TypeError):
            continue
    return aggregate(traces, sampled_at=current)
