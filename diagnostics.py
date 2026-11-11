"""Bounded local timings, without transcripts, credentials or provider payloads."""
from contextlib import closing, contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
import json
from pathlib import Path
import secrets
import sqlite3
from time import monotonic, time

DATABASE = Path(__file__).resolve().parent / '.data' / 'diagnostics.sqlite3'
ACTIVE = ContextVar('declan_request_trace', default=None)
RETENTION = 7 * 86400


def current_id():
    trace = ACTIVE.get()
    return trace['id'] if trace else None


@contextmanager
def request(route):
    trace = {'id': secrets.token_hex(12), 'route': route, 'created_at': time(),
             'stages': [], 'outcome': 'unknown'}
    token = ACTIVE.set(trace)
    trace['_started'] = monotonic()
    try:
        yield trace
    except Exception:
        trace['outcome'] = 'failed'
        raise
    finally:
        if '_saved' not in trace or trace['outcome'] == 'failed':
            persist(trace)
        ACTIVE.reset(token)


def persist(trace):
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


@contextmanager
def stage(name):
    trace = ACTIVE.get()
    started = monotonic()
    entry = {'stage': name, 'outcome': 'completed'}
    try:
        yield entry
    except Exception as error:
        entry['outcome'] = 'failed'
        # Deliberately omit exception text: URLs and headers may contain secrets.
        entry['error'] = type(error).__name__
        raise
    finally:
        entry['duration_ms'] = round((monotonic() - started) * 1000)
        if trace is not None and len(trace['stages']) < 80:
            trace['stages'].append(entry)


def timed(name):
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            with stage(name) as entry:
                result = function(*args, **kwargs)
                if isinstance(result, tuple) and len(result) > 1 and isinstance(result[1], str):
                    entry['outcome'] = result[1]
                elif isinstance(result, bool):
                    entry['outcome'] = 'confirmed' if result else 'unverified'
                return result
        return wrapped
    return decorate


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
