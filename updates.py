"""Stage a tagged Declan build, then atomically select it for systemd."""

import os
import json
import stat
import state_backup
import sqlite3
import re
import shutil
import subprocess
import sys
from http.client import HTTPException
from pathlib import Path
from tempfile import mkdtemp
from threading import Event, Lock, Thread
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


REPOSITORY = "https://github.com/NeoWeb-JP/Declan-2.0.git"
RELEASES_API = "https://api.github.com/repos/NeoWeb-JP/Declan-2.0/releases?per_page=100"
MAX_RELEASE_BYTES = 2 * 1024 * 1024
VERSION = re.compile(r"v?(\d{1,8})\.(\d{1,8})\.(\d{1,8})(?:-[0-9A-Za-z.-]{1,20})?")
APP = Path(__file__).resolve().parent
RESTART = Event()
_lock = Lock()
_tags = {}
_job = {"state": "idle"}


def trusted_releases():
    """Trust comes from the administrator, never the downloaded repository."""
    path = Path(os.environ.get("DECLAN_TRUSTED_RELEASES", "/etc/declan/trusted-releases.json"))
    if os.name != "posix" or not path.is_absolute():
        raise ValueError("A root-owned release allow-list is required.")
    for component in (path, *path.parents):
        info = component.lstat()
        if info.st_uid != 0 or info.st_mode & 0o022 or stat.S_ISLNK(info.st_mode):
            raise ValueError("Release allow-list and its parents must be root-owned and not writable by others.")
    pins = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(pins, dict) or not all(
            isinstance(tag, str) and VERSION.fullmatch(tag) and isinstance(sha, str)
            and re.fullmatch(r"[a-f0-9]{40}", sha) for tag, sha in pins.items()):
        raise ValueError("Invalid release allow-list.")
    return pins


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def release_source():
    source = os.environ.get('DECLAN_UPDATE_SOURCE', 'github').strip()
    if source not in {'github', 'pinned'}:
        raise ValueError('Choose github or pinned for DECLAN_UPDATE_SOURCE.')
    return source


def published_tags():
    """Only published stable releases in the fixed repository are candidates.

    GitHub publication is the trust boundary in the default channel. This is
    repository trust over HTTPS, not independent cryptographic release signing.
    Do not fetch code or assets from URLs returned in release metadata.
    """
    request = Request(RELEASES_API, headers={'Accept': 'application/vnd.github+json',
                                          'User-Agent': 'Declan-release-updater',
                                          'X-GitHub-Api-Version': '2022-11-28'})
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=10) as response:
            raw = response.read(MAX_RELEASE_BYTES + 1)
        if len(raw) > MAX_RELEASE_BYTES:
            raise ValueError('Release response too large')
        releases = json.loads(raw)
        if not isinstance(releases, list) or any(not isinstance(item, dict) for item in releases):
            raise ValueError('Invalid release list')
    except HTTPError as error:
        error.close()
        raise OSError('Could not read published GitHub releases.') from None
    except (ValueError, HTTPException):
        raise OSError('GitHub returned an invalid release list.') from None
    return {item['tag_name'] for item in releases
            if isinstance(item.get('tag_name'), str) and VERSION.fullmatch(item['tag_name'])
            and '-' not in item['tag_name'] and item.get('draft') is False
            and item.get('prerelease') is False and isinstance(item.get('published_at'), str)
            and bool(item['published_at'])}


def available_releases():
    source = release_source()
    pins = trusted_releases() if source == 'pinned' else None
    names = pins.keys() if pins is not None else published_tags()
    refs = run('git', 'ls-remote', '--tags', REPOSITORY, timeout=10)
    objects = {}
    for line in refs.splitlines():
        sha, separator, ref = line.partition('\trefs/tags/')
        if separator and re.fullmatch(r'[a-f0-9]{40}', sha):
            objects[ref] = sha
    tags = {}
    for name in names:
        if name not in objects:
            continue
        commit = objects.get(name + '^{}', objects[name])
        if pins is not None and pins[name] != commit:
            continue
        tags[name] = {'ref': objects[name], 'commit': commit, 'source': source}
    return tags


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
    # A failed check must not leave previously offered selections installable.
    with _lock:
        _tags.clear()
    if layout() is None:
        return []
    tags = available_releases()
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
        selection = dict(_tags[version])
        Thread(target=install, args=(root, version, selection), daemon=True).start()


def install(root, version, expected_ref):
    staged = None
    activated = False
    try:
        if os.environ.get("DECLAN_UPDATE_SUPERVISED") != "1":
            raise ValueError("Install the stable update supervisor before enabling updates.")
        if not isinstance(version, str) or not VERSION.fullmatch(version):
            raise ValueError('Invalid release tag')
        source = release_source()
        if isinstance(expected_ref, dict):
            selection = expected_ref
            if (set(selection) != {'ref', 'commit', 'source'} or selection['source'] != source
                    or any(not isinstance(selection[key], str) or not re.fullmatch(r'[a-f0-9]{40}', selection[key])
                           for key in ('ref', 'commit'))):
                raise ValueError('Check for updates again')
            # Recheck publication and tag identity before cloning or executing code.
            if available_releases().get(version) != selection:
                raise ValueError('Release was withdrawn or its tag changed. Check for updates again.')
            expected_ref, approved_commit = selection['ref'], selection['commit']
        elif source == 'pinned':
            # Compatibility for pinned-mode callers; the UI always passes a selection.
            approved_commit = trusted_releases().get(version)
            if approved_commit is None:
                raise ValueError('Release is not approved by the administrator.')
        else:
            raise ValueError('Check for updates before installing a published release.')
        staged = Path(mkdtemp(prefix=f"{version}-", dir=root / "releases"))
        run("git", "clone", "--quiet", "--depth", "1", "--branch", version, REPOSITORY, str(staged), timeout=90)
        ref = f"refs/tags/{version}"
        if (run("git", "rev-parse", ref, cwd=staged) != expected_ref
                or run("git", "rev-parse", "HEAD", cwd=staged) != approved_commit
                or run("git", "rev-parse", ref + "^{commit}", cwd=staged) != approved_commit):
            raise ValueError("Release tag changed")
        run(sys.executable, "-m", "venv", str(staged / ".venv"), timeout=90)
        python = str(staged / ".venv/bin/python")
        if (staged / "requirements-web-voice.txt").is_file():
            run(python, "-m", "pip", "--disable-pip-version-check", "install", "--require-hashes",
                "--only-binary=:all:", "-r", "requirements-web-voice.txt",
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
