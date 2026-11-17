"""Keep the operator environment reference as one valid Markdown table."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class EnvironmentReferenceTests(unittest.TestCase):
    def test_environment_variables_remain_in_one_table(self):
        content = (ROOT / "docs" / "environment.md").read_text(encoding="utf-8")
        section = content.split("## Variables documented for operators", 1)[1].split(
            "The added HA, Assist", 1
        )[0]
        rows = [line for line in section.splitlines() if line.startswith("|")]
        self.assertGreater(len(rows), 20)
        self.assertEqual(rows[0], "| Variable | Purpose | Example |")
        self.assertEqual(rows[1], "| --- | --- | --- |")
        self.assertEqual(rows, [line for line in section.splitlines() if line.strip()])
        names = [re.match(r"\| `([A-Z][A-Z0-9_]*)` \|", row) for row in rows[2:]]
        self.assertTrue(all(names), "Every environment table row needs a variable name")
        self.assertEqual(len(names), len({match.group(1) for match in names if match}))

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
