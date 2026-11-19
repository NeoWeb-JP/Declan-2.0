"""Ensure CI continues to enforce the mypy inventory guard."""
from pathlib import Path
import configparser
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "python-quality.yml"


class MypyWorkflowWiringTests(unittest.TestCase):
    def test_mypy_configuration_parses_and_checks_untyped_bodies(self):
        parser = configparser.ConfigParser(interpolation=None)
        with (ROOT / 'mypy.ini').open(encoding='utf-8') as configuration:
            parser.read_file(configuration)
        self.assertTrue(parser.getboolean('mypy', 'check_untyped_defs'))

    def test_advisory_inventory_is_followed_by_blocking_guard(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        inventory = workflow.index("- name: Mypy dependency import inventory (advisory)")
        guard = workflow.index("- name: Reject unexpected missing imports (blocking)")
        bandit = workflow.index("- name: Bandit security scan")
        self.assertLess(inventory, guard)
        self.assertLess(guard, bandit)
        guard_section = workflow[guard:bandit]
        self.assertIn("run: python scripts/check_mypy_imports.py", guard_section)
        self.assertNotIn("continue-on-error: true", guard_section)

    def test_inventory_records_exit_status_and_log(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        inventory = workflow.split(
            "- name: Mypy dependency import inventory (advisory)", 1
        )[1].split("- name: Reject unexpected missing imports (blocking)", 1)[0]
        self.assertIn("mypy-advisory.log", inventory)
        self.assertIn("mypy-advisory.exitcode", inventory)
        self.assertRegex(inventory, r"printf .*result.*mypy-advisory\.exitcode")


if __name__ == "__main__":
    unittest.main()
