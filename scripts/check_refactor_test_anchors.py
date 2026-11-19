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


def stale_anchors(test_text, removed):
    tree = ast.parse(test_text)
    sources = referenced_source_files(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in {"assertIn", "index", "find"}:
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        needle = node.args[0].value
        if not isinstance(needle, str) or not needle:
            continue
        if node.func.attr == "assertIn":
            if len(node.args) < 2 or not isinstance(node.args[1], ast.Name):
                continue
            variable = node.args[1].id
        elif isinstance(node.func.value, ast.Name):
            variable = node.func.value.id
        else:
            continue
        filename = sources.get(variable)
        if filename and filename in removed and needle in removed[filename]:
            yield node.lineno, filename, needle


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
        # Detect tests referencing a removed source expression, not merely
        # a string moved into a different module.
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr not in {"assertIn", "index", "find"} or not node.args:
                continue
            literal = node.args[0]
            if not isinstance(literal, ast.Constant) or not isinstance(literal.value, str):
                continue
            variable = None
            if node.func.attr == "assertIn" and len(node.args) > 1 and isinstance(node.args[1], ast.Name):
                variable = node.args[1].id
            elif isinstance(node.func.value, ast.Name):
                variable = node.func.value.id
            filename = sources.get(variable)
            if filename in removed:
                old, new = removed[filename]
                if literal.value and literal.value in old and literal.value not in new:
                    findings.append(f"{test.relative_to(root)}:{node.lineno}: {filename} no longer contains {literal.value!r}")
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
