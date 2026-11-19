"""Keep the operator environment reference as one valid Markdown table."""
from pathlib import Path
import re
import unittest
import configuration


ROOT = Path(__file__).resolve().parents[1]


class EnvironmentReferenceTests(unittest.TestCase):
    def test_every_inventory_variable_has_behavior_and_existing_test_evidence(self):
        content = (ROOT / "docs/environment.md").read_text(encoding="utf-8")
        inventory = content.split("## Verification scope", 1)[0]
        names = set(re.findall(r"^\| `([A-Z][A-Z0-9_]*)` \|", inventory, re.MULTILINE))
        self.assertEqual(set(configuration.FIELDS) - names, set(),
                         "Document indirect environment fallbacks for saved settings")
        behavior = content.split("## Verified runtime defaults and precedence", 1)[1].split(
            "### Persisted setting precedence", 1)[0]
        covered = set()
        for row in behavior.splitlines():
            if not row.startswith("| DECLAN_") and not row.startswith("| OPENAI_"):
                continue
            columns = row.split("|")[1:-1]
            self.assertEqual(len(columns), 4)
            covered.update(re.findall(r"DECLAN_[A-Z0-9_]+|OPENAI_API_KEY", columns[0]))
            self.assertTrue(columns[1].strip())
            self.assertTrue(columns[2].strip())
            tests = re.findall(r"`(tests/[^`]+\.py)`", columns[3])
            self.assertTrue(tests, row)
            for test in tests:
                self.assertTrue((ROOT / test).is_file(), test)
        self.assertEqual(names, covered)

    def test_environment_variables_remain_in_one_table(self):
        content = (ROOT / "docs" / "environment.md").read_text(encoding="utf-8")
        section = content.split("## Variables documented for operators", 1)[1].split(
            "\n## ", 1
        )[0].strip().split("\n\n", 1)[0]
        rows = [line for line in section.splitlines() if line.startswith("|")]
        self.assertGreater(len(rows), 20)
        self.assertEqual(rows[0], "| Variable | Purpose | Example |")
        self.assertEqual(rows[1], "| --- | --- | --- |")
        self.assertEqual(rows, [line for line in section.splitlines() if line.strip()])
        names = [re.match(r"\| `([A-Z][A-Z0-9_]*)` \|", row) for row in rows[2:]]
        self.assertTrue(all(names), "Every environment table row needs a variable name")
        self.assertEqual(len(names), len({match.group(1) for match in names if match}))
        all_names = re.findall(r"^\| `([A-Z][A-Z0-9_]*)` \|", content, re.MULTILINE)
        self.assertCountEqual(all_names, [match.group(1) for match in names if match],
                              "Operator variable rows must not be orphaned outside the table")

    def test_every_operator_variable_has_purpose_and_example(self):
        content = (ROOT / "docs" / "environment.md").read_text(encoding="utf-8")
        section = content.split("## Variables documented for operators", 1)[1].split(
            "\n## ", 1
        )[0].strip().split("\n\n", 1)[0]
        rows = [line for line in section.splitlines() if line.startswith("|")][2:]
        self.assertTrue(rows, "Expected documented operator variables")
        for row in rows:
            with self.subTest(row=row):
                columns = [column.strip() for column in row.split("|")[1:-1]]
                self.assertEqual(len(columns), 3, "Expected variable, purpose and example")
                self.assertTrue(columns[1], "Purpose must not be blank")
                self.assertTrue(columns[2], "Example or default guidance must not be blank")

    def test_active_example_assignments_have_documented_purposes(self):
        reference = (ROOT / "docs" / "environment.md").read_text(encoding="utf-8")
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        rows = {}
        for line in reference.splitlines():
            if not line.startswith("| `"):
                continue
            columns = [column.strip() for column in line.split("|")]
            if len(columns) >= 4 and columns[1].startswith("`"):
                rows[columns[1].strip("`")] = columns[2]
        active = re.findall(r"^([A-Z][A-Z0-9_]*)=(.*)$", example, re.MULTILINE)
        self.assertTrue(active, "Expected configured examples")
        for name, value in active:
            with self.subTest(variable=name):
                self.assertIn(name, rows)
                self.assertTrue(rows[name], "Document the purpose of each active setting")
                self.assertNotIn("\\n", value)

    def test_example_variables_are_documented(self):
        reference = (ROOT / "docs" / "environment.md").read_text(encoding="utf-8")
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        documented = set(re.findall(r"^\| `([A-Z][A-Z0-9_]*)` \|", reference, re.MULTILINE))
        example_names = set(re.findall(
            r"^\s*#?\s*(DECLAN_[A-Z0-9_]+)\s*=", example, re.MULTILINE
        ))
        self.assertTrue(example_names, "Expected environment variables in .env.example")
        self.assertEqual(set(), example_names - documented)


if __name__ == "__main__":
    unittest.main()
