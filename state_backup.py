"""Private local snapshots before update activation. Never uploaded by the UI."""
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import shutil
import sqlite3
from time import monotonic


def check(directory):
    directory = Path(directory)
    for source in sorted(directory.glob('*.sqlite3')):
        with closing(sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True, timeout=2)) as db:
            if db.execute('PRAGMA quick_check').fetchone() != ('ok',):
                raise ValueError('A persistent database failed its integrity check.')
    settings = directory / 'spotify-settings.json'
    if settings.exists():
        if not isinstance(json.loads(settings.read_text(encoding='utf-8')), dict):
            raise ValueError('Saved Spotify settings are invalid.')


def _redact_voice_samples(destination):
    """Never retain plaintext local voice recordings in new upgrade snapshots.

    Preserve profile/consent metadata for rollback while excluding audio blobs.
    Older snapshots are not modified by this function.
    """
    with closing(sqlite3.connect(destination, timeout=2)) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'samples' not in tables:
            return
        db.execute('PRAGMA secure_delete = ON')
        with db:
            db.execute('DELETE FROM samples')
        # Backup files must not retain deleted WAV bytes in free SQLite pages.
        db.execute('VACUUM')


def sanitize_retained_voice_snapshots(directory):
    """Remove legacy local voice audio from retained upgrade snapshots.

    Fail closed on unexpected files and avoid following symlinks. Each database
    is replaced only after a validated, redacted copy is ready.
    """
    root = Path(directory) / 'upgrade-backups'
    if not root.exists():
        return 0
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Upgrade backup directory is not a regular directory.')
    sanitized = 0
    failed = 0
    for folder in sorted(root.iterdir()):
        if folder.is_symlink() or not folder.is_dir():
            raise ValueError('Unexpected upgrade backup entry.')
        source = folder / 'voice-profiles.sqlite3'
        if not source.exists() and not source.is_symlink():
            continue
        if source.is_symlink() or not source.is_file():
            raise ValueError('Unexpected voice backup database entry.')
        temporary = folder / ('.voice-redaction-' + secrets.token_hex(8) + '.sqlite3')
        try:
            with closing(sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True, timeout=2)) as live, closing(sqlite3.connect(temporary, timeout=2)) as backup:
                if live.execute('PRAGMA quick_check').fetchone() != ('ok',):
                    raise ValueError('Legacy voice backup failed integrity check.')
                live.backup(backup)
            _redact_voice_samples(temporary)
            with closing(sqlite3.connect(temporary, timeout=2)) as check_db:
                if check_db.execute('PRAGMA quick_check').fetchone() != ('ok',):
                    raise ValueError('Redacted voice backup failed integrity check.')
            os.chmod(temporary, 0o600)
            os.replace(temporary, source)
            sanitized += 1
        except (OSError, ValueError, sqlite3.Error):
            failed += 1
        finally:
            temporary.unlink(missing_ok=True)
    if failed:
        raise ValueError(
            f'Voice backup cleanup incomplete: sanitized {sanitized} database(s); '
            f'{failed} database(s) require operator review.')
    return sanitized


def snapshot(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    check(directory)
    # Clean retained legacy copies before creating another snapshot.
    sanitize_retained_voice_snapshots(directory)
    root = directory / 'upgrade-backups'
    root.mkdir(mode=0o700, exist_ok=True)
    os.chmod(root, 0o700)
    name = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + secrets.token_hex(4)
    target = root / name
    target.mkdir(mode=0o700)
    try:
        for source in sorted(directory.glob('*.sqlite3')):
            destination = target / source.name
            with closing(sqlite3.connect(source, timeout=2)) as live, closing(sqlite3.connect(destination)) as backup:
                deadline = monotonic() + 10
                def progress(status, remaining, total):
                    if monotonic() >= deadline:
                        raise TimeoutError('Database snapshot exceeded its preparation window.')
                live.backup(backup, pages=128, progress=progress)
            if source.name == 'voice-profiles.sqlite3':
                _redact_voice_samples(destination)
            os.chmod(destination, 0o600)
        settings = directory / 'spotify-settings.json'
        if settings.exists():
            shutil.copyfile(settings, target / settings.name)
            os.chmod(target / settings.name, 0o600)
        check(target)
        (target / 'manifest.json').write_text(json.dumps({
            'schema_version': 1, 'created_at': name, 'files': sorted(p.name for p in target.iterdir()),
            'voice_samples': 'excluded_from_new_snapshots',
            'shared_state': 'Caches stay in the shared .data directory; HA integration storage requires an HA backup.'
        }), encoding='utf-8')
        os.chmod(target / 'manifest.json', 0o600)
    except Exception:
        shutil.rmtree(target)
        raise
    return name
