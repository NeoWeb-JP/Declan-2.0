"""Validate mypy missing imports while allowing Home Assistant runtime modules."""
from pathlib import Path
import re
import sys


IMPORT_ERROR = re.compile(r'error: .*?module named "([^"]+)"\s+\[import-not-found\]')


def unexpected_imports(text: str) -> list[str]:
    unexpected = []
    for line in text.splitlines():
        if "[import-not-found]" not in line:
            continue
        match = IMPORT_ERROR.search(line)
        # An unrecognised mypy diagnostic must not bypass the import guard.
        if match is None or not (
            match.group(1) == "homeassistant"
            or match.group(1).startswith("homeassistant.")
        ):
            unexpected.append(line)
    return unexpected


def main() -> int:
    path = Path("mypy-advisory.log")
    if not path.is_file():
        print("Missing mypy advisory inventory", file=sys.stderr)
        return 1
    status_file = Path("mypy-advisory.exitcode")
    if not status_file.is_file():
        print("Missing mypy advisory exit status", file=sys.stderr)
        return 1
    try:
        status = int(status_file.read_text(encoding="utf-8").strip())
    except ValueError:
        print("Invalid mypy advisory exit status", file=sys.stderr)
        return 1
    log = path.read_text(encoding="utf-8")
    if status not in (0, 1):
        print(f"Mypy inventory exited unexpectedly with status {status}", file=sys.stderr)
        return 1
    if status == 1 and "error:" not in log:
        print("Mypy inventory failed without diagnostics", file=sys.stderr)
        return 1
    unexpected = unexpected_imports(log)
    if unexpected:
        print("Unexpected non-Home Assistant missing imports", file=sys.stderr)
        print("\n".join(unexpected), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
