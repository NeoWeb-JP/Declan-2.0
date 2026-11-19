"""Flag source-location test assertions broken by a refactor.

Usage: python scripts/check_refactor_test_anchors.py --base-ref origin/main
This is a focused pre-PR aid, not a replacement for the full test suite.
"""

import argparse
import shutil
import ast
from pathlib import Path
import subprocess  # nosec B404
import sys


def source_at_ref(ref, path):
    result = subprocess.run(
        [shutil.which("git") or "/usr/bin/git", "show", f"{ref}:{path}"],
        capture_output=True, text=True, check=False,  # nosec B603: fixed git command, no shell
    )
    if result.returncode:
        raise RuntimeError(f"Cannot read {path} at {ref}: {result.stderr.strip()}")
    return result.stdout


def changed_python_files(ref):
    result = subprocess.run(
        [shutil.which("git") or "/usr/bin/git", "diff", "--name-only",
         "--diff-filter=ACMR", f"{ref}...HEAD"],
        capture_output=True, text=True, check=True,  # nosec B603: fixed git command, no shell
    )
    return [p for p in result.stdout.splitlines() if p.endswith(".py")]


def referenced_source_files(tree):
    """Recognise simple Path(...).read_text() assignments in test modules."""
    found = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = node.value
        if not isinstance(value, ast.Call) or not isinstance(value.func, ast.Attribute):
            continue
        if value.func.attr != "read_text":
            continue
        # Identify a literal Python filename anywhere in the expression.
        names = [n.value for n in ast.walk(value) if isinstance(n, ast.Constant)
                 and isinstance(n.value, str) and n.value.endswith(".py")]
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name) and names:
                found[target.id] = names[-1]
    return found


def anchor_references(tree):
    """Yield (line, source variable, literal) for common source-text contracts."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], ast.In):
            if isinstance(node.left, ast.Constant) and isinstance(node.left.value, str):
                if len(node.comparators) == 1 and isinstance(node.comparators[0], ast.Name):
                    yield node.lineno, node.comparators[0].id, node.left.value
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in {"assertIn", "index", "find", "count", "startswith", "endswith"}:
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        literal = node.args[0].value
        if not isinstance(literal, str):
            continue
        if node.func.attr == "assertIn":
            if len(node.args) >= 2 and isinstance(node.args[1], ast.Name):
                yield node.lineno, node.args[1].id, literal
        elif isinstance(node.func.value, ast.Name):
            yield node.lineno, node.func.value.id, literal



def check(base_ref, root):
    changed = changed_python_files(base_ref)
    removed = {}
    for path in changed:
        if path.startswith("tests/") or not (root / path).is_file():
            continue
        try:
            before = source_at_ref(base_ref, path)
        except RuntimeError:
            continue  # Newly added files have no base content.
        after = (root / path).read_text()
        if before != after:
            removed[Path(path).name] = before, after
    findings = []
    for test in sorted((root / "tests").rglob("test_*.py")):
        try:
            tree = ast.parse(test.read_text())
        except SyntaxError:
            continue  # Syntax checks are handled separately.
        sources = referenced_source_files(tree)
        # Check both unittest assertions and plain source-text assertions.
        for line, variable, literal in anchor_references(tree):
            filename = sources.get(variable)
            if filename in removed:
                old, new = removed[filename]
                if literal and literal in old and literal not in new:
                    findings.append(
                        f"{test.relative_to(root)}:{line}: "
                        f"{filename} no longer contains {literal!r}"
                    )
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", default="origin/main")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        findings = check(args.base_ref, root)
    except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
        print(f"Refactor anchor check unavailable: {exc}", file=sys.stderr)
        return 2
    for finding in findings:
        print(finding)
    print(f"Refactor source-location check: {len(findings)} potential stale assertions")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
