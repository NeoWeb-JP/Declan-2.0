"""Cross-platform regression tests for the mypy import guard used by CI."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "check_mypy_imports.py"


class MypyImportGuardTests(unittest.TestCase):
    def run_guard(self, log, status=None):
        with tempfile.TemporaryDirectory() as directory:
            workdir = Path(directory)
            if log is not None:
                (workdir / "mypy-advisory.log").write_text(log, encoding="utf-8")
                (workdir / "mypy-advisory.exitcode").write_text(
                    str(status if status is not None else (1 if "error:" in log else 0)),
                    encoding="utf-8",
                )
            result = subprocess.run(
                [sys.executable, str(GUARD)], cwd=workdir,
                capture_output=True, text=True, check=False,
            )
            return result.returncode, result.stdout + result.stderr

    def test_home_assistant_import_is_allowed(self):
        code, output = self.run_guard(
            'integration.py:1: error: Cannot find implementation or library stub for module named "homeassistant.helpers"  [import-not-found]\n'
        )
        self.assertEqual(code, 0, output)

    def test_other_missing_import_is_rejected(self):
        code, output = self.run_guard(
            'integration.py:1: error: Cannot find implementation or library stub for module named "unavailable_library"  [import-not-found]\n'
        )
        self.assertNotEqual(code, 0)
        self.assertIn("unavailable_library", output)

    def test_homeassistant_prefix_is_not_exempt(self):
        code, output = self.run_guard(
            'integration.py:1: error: Cannot find module named "homeassistant_fake"  [import-not-found]\n'
        )
        self.assertNotEqual(code, 0)
        self.assertIn("homeassistant_fake", output)

    def test_unrecognised_import_diagnostic_fails_closed(self):
        code, output = self.run_guard(
            'integration.py:1: error: missing dependency [import-not-found]\n'
        )
        self.assertNotEqual(code, 0)
        self.assertIn("missing dependency", output)

    def test_inventory_crash_without_diagnostics_is_rejected(self):
        code, output = self.run_guard("mypy: internal failure\n", status=2)
        self.assertNotEqual(code, 0)
        self.assertIn("exited unexpectedly", output)

    def test_mypy_crash_with_error_text_is_rejected(self):
        code, output = self.run_guard("mypy: error: internal failure\n", status=2)
        self.assertNotEqual(code, 0)
        self.assertIn("exited unexpectedly", output)

    def test_mypy_diagnostic_failure_without_errors_is_rejected(self):
        code, output = self.run_guard("mypy: unexpected output\n", status=1)
        self.assertNotEqual(code, 0)
        self.assertIn("failed without diagnostics", output)

    def test_successful_empty_inventory_is_allowed(self):
        code, output = self.run_guard("Success: no issues found\n", status=0)
        self.assertEqual(code, 0, output)

    def test_missing_inventory_is_rejected(self):
        code, output = self.run_guard(None)
        self.assertNotEqual(code, 0)
        self.assertIn("Missing mypy advisory inventory", output)


if __name__ == "__main__":
    unittest.main()
