"""Exercise the blocking missing-import guard from the actual CI workflow."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/python-quality.yml"
STEP = "      - name: Reject unexpected missing imports (blocking)"


@unittest.skipIf(sys.platform == "win32", "CI guard uses Bash on Ubuntu")
class MypyImportGuardTests(unittest.TestCase):
    @staticmethod
    def guard_script():
        workflow = WORKFLOW.read_text(encoding="utf-8")
        section = workflow.split(STEP, 1)[1].split("\n      - name:", 1)[0]
        return "\n".join(line[10:] for line in section.splitlines()[3:])

    def run_guard(self, log):
        with tempfile.TemporaryDirectory() as directory:
            workdir = Path(directory)
            if log is not None:
                (workdir / "mypy-advisory.log").write_text(log, encoding="utf-8")
            result = subprocess.run(
                ["bash", "-e", "-c", self.guard_script()],
                cwd=workdir,
                capture_output=True,
                text=True,
                check=False,
            )
            return result.returncode, result.stdout + result.stderr

    def test_home_assistant_import_is_allowed(self):
        code, output = self.run_guard(
            'integration.py:1: error: Cannot find module named "homeassistant.helpers"  [import-not-found]\n'
        )
        self.assertEqual(code, 0, output)

    def test_other_missing_import_is_rejected(self):
        code, output = self.run_guard(
            'integration.py:1: error: Cannot find module named "unavailable_library"  [import-not-found]\n'
        )
        self.assertNotEqual(code, 0)
        self.assertIn("unavailable_library", output)

    def test_missing_inventory_is_rejected(self):
        code, output = self.run_guard(None)
        self.assertNotEqual(code, 0)
        self.assertIn("Missing mypy advisory inventory", output)


if __name__ == "__main__":
    unittest.main()
