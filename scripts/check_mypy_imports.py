"""Validate mypy missing imports while allowing Home Assistant runtime modules."""
from pathlib import Path
import re
import sys


IMPORT_ERROR = re.compile(r'error: .*?module named "([^"]+)"\s+\[import-not-found\]')


def unexpected_imports(text: str) -> list[str]:
    return [line for line in text.splitlines()
            if (match := IMPORT_ERROR.search(line)) and
            not (match.group(1) == "homeassistant" or
                 match.group(1).startswith("homeassistant."))]


def main() -> int:
    path = Path("mypy-advisory.log")
    if not path.is_file():
        print("Missing mypy advisory inventory", file=sys.stderr)
        return 1
    unexpected = unexpected_imports(path.read_text(encoding="utf-8"))
    if unexpected:
        print("Unexpected non-Home Assistant missing imports", file=sys.stderr)
        print("\n".join(unexpected), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
