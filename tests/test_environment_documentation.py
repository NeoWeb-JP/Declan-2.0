"""Keep documented runtime environment settings aligned with backend reads."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
ENV_READ = re.compile(
    r"""(?:\b(?:os\.)?getenv\s*\(\s*|\b(?:os\.)?environ(?:\.(?:get|setdefault|pop)\s*\(\s*|\[\s*))['"]((?:DECLAN_[A-Z0-9_]+|OPENAI_API_KEY))['"]"""
)
DOCUMENTED = re.compile(r"^\|\s*\`((?:DECLAN_[A-Z0-9_]+|OPENAI_API_KEY))\`\s*\|", re.MULTILINE)


class EnvironmentDocumentationTests(unittest.TestCase):
    def test_detects_supported_environment_read_forms(self):
        examples = (
            'os.getenv("DECLAN_EXAMPLE")',
            'getenv("DECLAN_EXAMPLE")',
            'os.environ.get("DECLAN_EXAMPLE", "default")',
            'environ.get("DECLAN_EXAMPLE")',
            'os.environ["DECLAN_EXAMPLE"]',
            'environ["DECLAN_EXAMPLE"]',
            'os.environ.setdefault("DECLAN_EXAMPLE", "fallback")',
            'os.environ.pop("DECLAN_EXAMPLE", None)',
            'environ.setdefault("DECLAN_EXAMPLE", "fallback")',
            'environ.pop("DECLAN_EXAMPLE", None)',
            'os.environ.get("OPENAI_API_KEY")',
        )
        for expression in examples:
            with self.subTest(expression=expression):
                self.assertEqual(ENV_READ.findall(expression), [
                    "OPENAI_API_KEY" if "OPENAI_API_KEY" in expression else "DECLAN_EXAMPLE"
                ])

    def test_repository_environment_reads_are_documented(self):
        """Audit every production Python module, including newly added modules."""
        documented = set(DOCUMENTED.findall(
            (ROOT / "docs/environment.md").read_text(encoding="utf-8")
        ))
        missing = {}
        for file in ROOT.rglob("*.py"):
            relative = file.relative_to(ROOT)
            if any(part in {"tests", ".git", ".venv", "venv", "node_modules"}
                   for part in relative.parts):
                continue
            source = file.read_text(encoding="utf-8")
            undocumented = sorted(set(ENV_READ.findall(source)) - documented)
            if undocumented:
                missing[relative.as_posix()] = undocumented
        self.assertEqual(missing, {}, "Document production environment reads")

    def test_environment_inventory_has_unique_described_entries(self):
        """Each environment setting needs one meaningful purpose and example."""
        inventory = (ROOT / "docs/environment.md").read_text(encoding="utf-8")
        entries = []
        incomplete = []
        for line in inventory.splitlines():
            match = DOCUMENTED.match(line)
            if match is None:
                continue
            columns = [column.strip() for column in line.strip().strip("|").split("|")]
            key = match.group(1)
            entries.append(key)
            if len(columns) < 3 or not columns[1] or not columns[2]:
                incomplete.append(key)
        self.assertEqual(incomplete, [], "Document a purpose and example for each setting")
        duplicates = sorted({key for key in entries if entries.count(key) > 1})
        self.assertEqual(duplicates, [], "Each environment setting needs one inventory row")

    def test_example_environment_keys_have_no_unrecognized_names(self):
        """Catch typoed configuration keys that the application will ignore."""
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        assigned = set(re.findall(
            r"^\\s*#?\\s*([A-Z][A-Z0-9_]*)\\s*=",
            example,
            re.MULTILINE,
        ))
        documented = set(DOCUMENTED.findall(
            (ROOT / "docs/environment.md").read_text(encoding="utf-8")
        ))
        self.assertEqual(
            sorted(assigned - documented),
            [],
            "Every .env.example assignment must have a documented environment key",
        )

    def test_example_environment_keys_are_documented(self):
        documented = set(DOCUMENTED.findall((ROOT / "docs/environment.md").read_text(encoding="utf-8")))
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        example_keys = re.findall(
            r"^\s*#?\s*((?:DECLAN_[A-Z0-9_]+|OPENAI_API_KEY))\s*=",
            example,
            re.MULTILINE,
        )
        self.assertEqual(sorted(set(example_keys) - documented), [], "Document .env.example keys")
        duplicates = sorted({key for key in example_keys if example_keys.count(key) > 1})
        self.assertEqual(duplicates, [], "Do not define the same .env.example key twice")


if __name__ == "__main__":
    unittest.main()
