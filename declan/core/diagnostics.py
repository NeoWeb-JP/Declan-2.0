"""Bounded local timings, without transcripts, credentials or provider payloads."""
from contextlib import closing, contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import StrEnum
from functools import wraps
import json
from pathlib import Path
import secrets
import sqlite3
from time import monotonic, time
from typing import Any

from declan.core.execution_results import ExecutionResult, Outcome, parse_outcome

DATABASE = Path(__file__).resolve().parent / '.data' / 'diagnostics.sqlite3'
ACTIVE: ContextVar[dict[str, Any] | None] = ContextVar('declan_request_trace', default=None)
RETENTION = 7 * 86400


class DiagnosticOutcome(StrEnum):
    UNKNOWN = 'unknown'
    COMPLETED = 'completed'
    FAILED = 'failed'


@dataclass(frozen=True)
class DiagnosticResult:
    status: DiagnosticOutcome | Outcome | None
    wire_value: Any

    def __post_init__(self):
        if self.status is not None:
            if not isinstance(self.status, (DiagnosticOutcome, Outcome)):
                raise TypeError('status must be a diagnostic or execution outcome')
            if self.wire_value != self.status.value:
                raise ValueError('wire outcome must match its recognized status')

    @classmethod
    def from_value(cls, value) -> 'DiagnosticResult':
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            try:
                status = DiagnosticOutcome(value)
                return cls(status, status.value)
            except ValueError:
                outcome = parse_outcome(value)
                if outcome is not None:
                    return cls(outcome, outcome.value)
        return cls(None, value)


def set_outcome(trace, value):
    result = DiagnosticResult.from_value(value)
    trace['outcome'] = result.wire_value


def outcome_result(trace) -> DiagnosticResult:
    return DiagnosticResult.from_value(trace.get('outcome'))


def timed_result(value) -> DiagnosticResult:
    if isinstance(value, ExecutionResult):
        return DiagnosticResult.from_value(value.outcome)
    if isinstance(value, tuple) and value and isinstance(value[0], ExecutionResult):
        return DiagnosticResult.from_value(value[0].outcome)
    if isinstance(value, tuple) and len(value) > 1 and isinstance(value[1], str):
        return DiagnosticResult.from_value(value[1])
    if isinstance(value, bool):
        return DiagnosticResult.from_value(Outcome.CONFIRMED if value else Outcome.UNVERIFIED)
    return DiagnosticResult.from_value(DiagnosticOutcome.COMPLETED)


def current_id():
    trace = ACTIVE.get()
    return trace['id'] if trace else None


@contextmanager
def request(route):
    trace = {'id': secrets.token_hex(12), 'route': route, 'created_at': time(),
             'stages': []}
    set_outcome(trace, DiagnosticOutcome.UNKNOWN)
    token = ACTIVE.set(trace)
    trace['_started'] = monotonic()
    try:
        yield trace
    except Exception:
        set_outcome(trace, DiagnosticOutcome.FAILED)
        raise
    finally:
        if '_saved' not in trace or outcome_result(trace).status is DiagnosticOutcome.FAILED:
            persist(trace)
        ACTIVE.reset(token)


def persist(trace):
    set_outcome(trace, outcome_result(trace))
    trace['duration_ms'] = round((monotonic() - trace['_started']) * 1000)
    try:
        DATABASE.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(DATABASE, timeout=0.1)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS traces (id TEXT PRIMARY KEY, created_at REAL, payload TEXT)')
            payload = {key: value for key, value in trace.items() if not key.startswith('_')}
            db.execute('INSERT OR REPLACE INTO traces VALUES (?, ?, ?)', (trace['id'], trace['created_at'], json.dumps(payload)))
            db.execute('DELETE FROM traces WHERE created_at < ?', (time() - RETENTION,))
            db.execute('DELETE FROM traces WHERE id NOT IN (SELECT id FROM traces ORDER BY created_at DESC LIMIT 500)')
        trace['_saved'] = True
    except (OSError, sqlite3.Error):
        # Diagnostics must never stop a household action or cause a retry.
        pass


def amend(trace, entry):
    """Append a late stage (for example a background check) to a saved trace.

    Unlike persist(), this keeps the request's own duration and outcome: the
    caller already got its reply, and only the extra evidence is added.
    """
    if not isinstance(trace, dict) or '_saved' not in trace or len(trace['stages']) >= 80:
        return
    trace['stages'].append({key: value for key, value in entry.items() if not key.startswith('_')})
    try:
        with closing(sqlite3.connect(DATABASE, timeout=0.1)) as db, db:
            payload = {key: value for key, value in trace.items() if not key.startswith('_')}
            db.execute('UPDATE traces SET payload = ? WHERE id = ?', (json.dumps(payload), trace['id']))
    except (OSError, sqlite3.Error):
        # Diagnostics must never stop a household action or cause a retry.
        pass


def record(name, started, **fields):
    """Append an already-finished stage that began at monotonic() == started."""
    trace = ACTIVE.get()
    if trace is None or len(trace['stages']) >= 80:
        return
    entry = {'stage': name}
    set_outcome(entry, DiagnosticOutcome.COMPLETED)
    entry.update(fields)
    entry['duration_ms'] = round((monotonic() - started) * 1000)
    trace['stages'].append({key: value for key, value in entry.items() if not key.startswith('_')})


@contextmanager
def stage(name):
    trace = ACTIVE.get()
    started = monotonic()
    entry = {'stage': name}
    set_outcome(entry, DiagnosticOutcome.COMPLETED)
    try:
        yield entry
    except Exception as error:
        set_outcome(entry, DiagnosticOutcome.FAILED)
        # Deliberately omit exception text: URLs and headers may contain secrets.
        entry['error'] = type(error).__name__
        raise
    finally:
        entry['duration_ms'] = round((monotonic() - started) * 1000)
        if trace is not None and len(trace['stages']) < 80:
            trace['stages'].append({key: value for key, value in entry.items() if not key.startswith('_')})


def timed(name):
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            with stage(name) as entry:
                result = function(*args, **kwargs)
                set_outcome(entry, timed_result(result))
                return result
        return wrapped
    return decorate


def metrics():
    """Return a bounded, privacy-safe aggregate over the last 24 hours."""
    from declan.core import diagnostic_metrics
    return diagnostic_metrics.summary(DATABASE, retention=RETENTION)


def recent():
    if not DATABASE.exists():
        return []
    with closing(sqlite3.connect(DATABASE, timeout=0.1)) as db, db:
        rows = db.execute('SELECT payload FROM traces WHERE created_at >= ? ORDER BY created_at DESC LIMIT 50',
                          (time() - RETENTION,)).fetchall()
    traces = [json.loads(row[0]) for row in rows]
    for trace in traces:
        trace['created_at'] = datetime.fromtimestamp(trace['created_at'], timezone.utc).isoformat()
    return traces
