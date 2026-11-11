"""Stable systemd launcher. Install outside releases so broken updates can roll back."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
from time import monotonic, sleep
from urllib.request import ProxyHandler, build_opener


def healthy(opener, port, process, timeout=30):
    deadline = monotonic() + timeout
    while process.poll() is None and monotonic() < deadline:
        try:
            with opener.open(f"http://127.0.0.1:{port}/health", timeout=1) as response:
                if (response.headers.get("X-Declan-Pid") == str(process.pid)
                        and json.loads(response.read(4096)) == {"status": "ok"}
                        and process.poll() is None):
                    return True
        except (OSError, ValueError):
            pass
        sleep(0.25)
    return False


def select(root, target):
    pending = root / ".supervisor-current"
    pending.unlink(missing_ok=True)
    pending.symlink_to(target, target_is_directory=True)
    os.replace(pending, root / "current")


def stop(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def supervise(root, port=52737, *, launch=subprocess.Popen):
    opener = build_opener(ProxyHandler({}))
    child = None
    stopping = False

    def shutdown(signum, frame):
        nonlocal stopping
        stopping = True
        if child is not None:
            stop(child)

    previous_handlers = {s: signal.signal(s, shutdown) for s in (signal.SIGTERM, signal.SIGINT)}
    try:
        while not stopping:
            selected = (root / "current").resolve(strict=True)
            try:
                child = launch([str(selected / ".venv/bin/python"), str(selected / "server.py"),
                                "--assist-lan", "--port", str(port)], cwd=selected,
                               env={**os.environ, "DECLAN_UPDATE_SUPERVISED": "1"})
                ready = healthy(opener, port, child)
            except OSError:
                ready = False
            if stopping:
                return 0
            if not ready:
                if child is not None:
                    stop(child)
                if not (root / "previous").exists():
                    return 1
                previous = (root / "previous").resolve(strict=True)
                if previous == selected or not (previous / "server.py").is_file():
                    return 1
                print("Selected release failed its startup health check; restoring previous release.", flush=True)
                select(root, previous)
                # If rollback fails too, exit for systemd instead of alternating builds.
                (root / "previous").unlink()
                (root / "previous").symlink_to(previous, target_is_directory=True)
                child = None
                continue
            # Import cleanup only from this stable installed module, not the new release.
            try:
                prune_old(root, selected / ".data")
            except Exception as error:
                print(f"Release cleanup failed: {type(error).__name__}", flush=True)
            result = child.wait()
            child = None
            if stopping or result != 75:
                return result
    finally:
        if child is not None:
            stop(child)
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)


def prune_old(root, data, keep=3):
    # Keep this launcher self-contained when copied outside the checkout.
    import shutil
    protected = {(root / name).resolve() for name in ("current", "previous")}
    for directory in (root / "releases", data / "upgrade-backups"):
        if directory.is_symlink() or not directory.is_dir():
            continue
        entries = sorted((p for p in directory.iterdir() if p.is_dir() and not p.is_symlink()),
                         key=lambda p: p.stat().st_mtime, reverse=True)
        for entry in entries[keep:]:
            if entry.resolve() not in protected:
                shutil.rmtree(entry)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--port", type=int, default=52737)
    args = parser.parse_args()
    raise SystemExit(supervise(args.root, args.port))
