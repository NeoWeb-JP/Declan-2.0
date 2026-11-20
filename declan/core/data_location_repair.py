"""Recover data written to the wrong folder by releases 2.13.0 and 2.13.1-rc1.

Those releases moved history.py and diagnostics.py into declan/core/ but kept a
``Path(__file__).parent / ".data"`` path. Declan therefore created a new, empty
conversations database at ``declan/core/.data`` inside the release directory and
stopped seeing the shared ``.data/conversations.sqlite3``.

On startup this module finds those release-local databases (in this release,
``previous`` and every directory under ``releases/``) and merges what the owner
did while they were in use into the shared database:

- learned_intents: upserted; a phrase taught on 2.13 wins over the older one.
- turns: appended, skipping exact duplicates.
- ai_budget: monthly reservations added, so AI spending is never under-counted.

Settings-like tables (server settings, AI settings, routines, responses) are not
merged automatically: the release-local copies may contain startup defaults that
would overwrite the owner's real configuration. Their row counts are logged and
the release-local file is kept (renamed to ``*.merged-<timestamp>``) so anything
changed on 2.13 can be recovered by hand.

The shared database is never deleted or replaced, except that when it does not
exist at all the release-local database is copied into place unchanged.
"""
from __future__ import annotations

import re
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path
from time import time

_NAME = "conversations.sqlite3"
_RELATIVE = Path("declan") / "core" / ".data" / _NAME
_MERGED = ("learned_intents", "turns", "ai_budget")
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_SCHEMAS = frozenset({"main", "stray"})


def _identifier(name: str) -> str:
    """Only plain SQLite identifiers (read from the database itself) are interpolated."""
    if not isinstance(name, str) or not _IDENTIFIER.match(name):
        raise sqlite3.DatabaseError(f"Unexpected identifier {name!r}")
    return name


def candidates(app: Path) -> list[Path]:
    """Release-local conversation databases that may hold 2.13 data, oldest first."""
    app = Path(app)
    paths = [app / _RELATIVE]
    root = app.parent.parent if app.parent.name == "releases" else None
    if root is not None:
        paths.append(root / "previous" / _RELATIVE)
        releases = root / "releases"
        try:
            paths.extend(sorted(releases.glob(f"*/{_RELATIVE.as_posix()}"),
                                key=lambda path: path.stat().st_mtime))
        except OSError:
            pass
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        try:
            if not path.is_file():
                continue
            resolved = path.resolve()
        except OSError:
            continue
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    return unique


def _tables(db: sqlite3.Connection, schema: str) -> set[str]:
    if schema not in _SCHEMAS:
        raise ValueError(schema)
    query = f"SELECT name FROM {schema}.sqlite_master WHERE type = 'table'"  # nosec B608 - schema is a fixed constant
    return {name for (name,) in db.execute(query) if _IDENTIFIER.match(name)}


def _columns(db: sqlite3.Connection, schema: str, table: str) -> list[str]:
    if schema not in _SCHEMAS:
        raise ValueError(schema)
    return [_identifier(row[1]) for row in db.execute(f"PRAGMA {schema}.table_info({_identifier(table)})")]


def _checkpoint(path: Path) -> None:
    with closing(sqlite3.connect(path, timeout=2)) as db:
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def _retire(path: Path, stamp: int) -> Path:
    retired = path.with_name(f"{path.name}.merged-{stamp}")
    path.rename(retired)
    for suffix in ("-wal", "-shm"):
        side = path.with_name(path.name + suffix)
        if side.exists():
            side.unlink()
    return retired


def merge(stray: Path, target: Path) -> dict:
    """Merge one release-local database into the shared one, in one transaction."""
    report: dict = {"source": str(stray), "learned_intents": 0, "turns": 0, "ai_budget_months": 0,
                    "not_merged": {}}
    _checkpoint(stray)
    with closing(sqlite3.connect(target, timeout=5)) as db:
        db.execute("ATTACH DATABASE ? AS stray", (str(stray),))
        try:
            source_tables = _tables(db, "stray")
            target_tables = _tables(db, "main")
            with db:
                if "learned_intents" in source_tables:
                    db.execute("CREATE TABLE IF NOT EXISTS learned_intents "
                               "(phrase TEXT PRIMARY KEY, target TEXT NOT NULL)")
                    report["learned_intents"] = db.execute(
                        "INSERT INTO main.learned_intents(phrase, target) "
                        "SELECT phrase, target FROM stray.learned_intents WHERE true "
                        "ON CONFLICT(phrase) DO UPDATE SET target = excluded.target").rowcount
                if "turns" in source_tables and "turns" in target_tables:
                    shared = [c for c in _columns(db, "stray", "turns")
                              if c != "id" and c in set(_columns(db, "main", "turns"))]
                    if {"created_at", "session_id", "message"} <= set(shared):
                        names = ", ".join(_identifier(column) for column in shared)
                        insert = (f"INSERT INTO main.turns({names}) SELECT {names} FROM stray.turns s "  # nosec B608 - validated column identifiers
                                  "WHERE NOT EXISTS (SELECT 1 FROM main.turns m WHERE m.created_at = s.created_at "
                                  "AND m.session_id = s.session_id AND m.message = s.message)")
                        report["turns"] = db.execute(insert).rowcount
                if "ai_budget" in source_tables:
                    db.execute("CREATE TABLE IF NOT EXISTS ai_budget (month TEXT PRIMARY KEY, reserved INTEGER NOT NULL)")
                    report["ai_budget_months"] = db.execute(
                        "INSERT INTO main.ai_budget(month, reserved) "
                        "SELECT month, reserved FROM stray.ai_budget WHERE reserved > 0 "
                        "ON CONFLICT(month) DO UPDATE SET reserved = reserved + excluded.reserved").rowcount
                for table in sorted(source_tables - set(_MERGED)):
                    if table.startswith("sqlite_"):
                        continue
                    count_query = f'SELECT count(*) FROM stray."{_identifier(table)}"'  # nosec B608 - validated table identifier
                    count = db.execute(count_query).fetchone()[0]
                    if count:
                        report["not_merged"][table] = count
        finally:
            db.execute("DETACH DATABASE stray")
    return report


def repair(app: Path, target: Path, *, logger=None, now=time) -> list[dict]:
    """Merge every release-local database into ``target``; safe to run on each start."""
    target = Path(target)
    reports = []
    stamp = int(now())
    for stray in candidates(app):
        try:
            if target.exists() and stray.resolve() == target.resolve():
                continue
            if not target.exists():
                _checkpoint(stray)
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(target.name + ".recovering")
                shutil.copy2(stray, temporary)
                temporary.replace(target)
                report = {"source": str(stray), "copied": True}
            else:
                report = merge(stray, target)
            report["kept_as"] = str(_retire(stray, stamp))
        except (OSError, sqlite3.Error) as error:
            if logger is not None:
                logger.error("Could not recover release-local Declan data from %s: %s", stray, error)
            continue
        reports.append(report)
        if logger is not None:
            logger.warning(
                "Recovered Declan data written by 2.13.x to %s: %s learned phrases, %s history turns, "
                "%s AI budget months merged into %s. Not merged (re-enter if changed on 2.13): %s. "
                "Original kept as %s.",
                report["source"], report.get("learned_intents", "all"), report.get("turns", "all"),
                report.get("ai_budget_months", "all"), target,
                report.get("not_merged") or "nothing", report["kept_as"])
    return reports
