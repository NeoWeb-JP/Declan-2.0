"""Stage a tagged Declan build, then atomically select it for systemd."""

import os
import state_backup
import sqlite3
import re
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import mkdtemp
from threading import Event, Lock, Thread


REPOSITORY = "https://github.com/NeoWeb-JP/Declan-2.0.git"
VERSION = re.compile(r"v?(\d{1,8})\.(\d{1,8})\.(\d{1,8})(?:-[0-9A-Za-z.-]{1,20})?")
APP = Path(__file__).resolve().parent
RESTART = Event()
_lock = Lock()
_tags = {}
_job = {"state": "idle"}


def run(*command, cwd=None, timeout=30):
    return subprocess.run(command, cwd=cwd, check=True, capture_output=True, text=True,
                          timeout=timeout, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}).stdout.strip()


def layout():
    configured = os.environ.get("DECLAN_UPDATE_ROOT")
    if not configured or os.name != "posix":
        return None
    root = Path(configured)
    current = root / "current"
    releases = root / "releases"
    if (root.is_absolute() and current.is_symlink() and current.resolve() == APP
            and releases.is_dir() and os.access(root, os.W_OK) and os.access(releases, os.W_OK)):
        return root
    return None


def installed_version(fallback):
    try:
        version = (APP / ".declan-release").read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return fallback
    return version if VERSION.fullmatch(version) else fallback


def status():
    with _lock:
        return {"enabled": layout() is not None, **_job}


def check():
    if layout() is None:
        return []
    refs = run("git", "ls-remote", "--tags", "--refs", REPOSITORY, timeout=10)
    tags = {}
    for line in refs.splitlines():
        sha, _, ref = line.partition("\trefs/tags/")
        if VERSION.fullmatch(ref) and re.fullmatch(r"[a-f0-9]{40}", sha):
            tags[ref] = sha
    with _lock:
        _tags.clear()
        _tags.update(tags)
    return sorted(tags, key=lambda tag: (*map(int, VERSION.fullmatch(tag).groups()), "-" not in tag, tag), reverse=True)


def queue(version, current):
    root = layout()
    if root is None:
        raise ValueError("Updates are not enabled on this installation.")
    with _lock:
        if _job["state"] in {"installing", "restarting"}:
            raise ValueError("An update is already in progress.")
        if not isinstance(version, str) or version not in _tags or version == current:
            raise ValueError("Check for updates and select a different release.")
        _job.update(state="installing", version=version)
        Thread(target=install, args=(root, version, _tags[version]), daemon=True).start()


def install(root, version, expected_ref):
    staged = None
    activated = False
    try:
        staged = Path(mkdtemp(prefix=f"{version}-", dir=root / "releases"))
        run("git", "clone", "--quiet", "--depth", "1", "--branch", version, REPOSITORY, str(staged), timeout=90)
        ref = f"refs/tags/{version}"
        if (run("git", "rev-parse", ref, cwd=staged) != expected_ref
                or run("git", "rev-parse", "HEAD", cwd=staged) != run("git", "rev-parse", ref + "^{commit}", cwd=staged)):
            raise ValueError("Release tag changed")
        run(sys.executable, "-m", "venv", str(staged / ".venv"), timeout=90)
        python = str(staged / ".venv/bin/python")
        if (staged / "requirements-web-voice.txt").is_file():
            run(python, "-m", "pip", "--disable-pip-version-check", "install", "-r", "requirements-web-voice.txt",
                cwd=staged, timeout=180)
        run(python, "server.py", "--help", cwd=staged)
        (staged / ".data").symlink_to((APP / ".data").resolve(), target_is_directory=True)
        (staged / ".declan-release").write_text(version + "\n", encoding="ascii")
        if layout() != root:
            raise ValueError("Active release changed during staging")
        backup = state_backup.snapshot(APP / ".data")
        with _lock:
            _job.update(backup=backup)
        for name, target in (("previous", APP), ("current", staged)):
            pending = root / f".{name}-{staged.name}"
            pending.symlink_to(target, target_is_directory=True)
            try:
                os.replace(pending, root / name)
            finally:
                pending.unlink(missing_ok=True)
        activated = True
        with _lock:
            _job.update(state="restarting")
        RESTART.set()
    except (OSError, ValueError, sqlite3.Error, subprocess.SubprocessError) as error:
        print(f"Declan update {version} failed: {type(error).__name__}", flush=True)
        with _lock:
            _job.update(state="failed")
    finally:
        if staged is not None and not activated:
            shutil.rmtree(staged, ignore_errors=True)
