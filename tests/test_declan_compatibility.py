"""Regression tests for the version compatibility contract."""
import importlib.util
from pathlib import Path
import unittest


MODULE = Path(__file__).resolve().parents[1] / "custom_components" / "declan_two" / "compatibility.py"
spec = importlib.util.spec_from_file_location("declan_compatibility", MODULE)
module = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = module
spec.loader.exec_module(module)


class CompatibilityTests(unittest.TestCase):
    def test_matching_api_major_accepts_independent_server_version(self):
        result = module.check_server_compatibility({"server_version": "0.12.7", "api_version": "1.2"})
        self.assertTrue(result.compatible)
        self.assertEqual(result.server_version, "0.12.7")

    def test_missing_version_fails_closed(self):
        self.assertFalse(module.check_server_compatibility({"server_version": "0.12.7"}).compatible)

    def test_future_major_fails_closed(self):
        self.assertFalse(module.check_server_compatibility({"api_version": "2.0"}).compatible)

    def test_invalid_version_fails_closed(self):
        for value in ("", "one", "1.", "1.beta", 1, None):
            with self.subTest(value=value):
                self.assertFalse(module.check_server_compatibility({"api_version": value}).compatible)


if __name__ == "__main__":
    unittest.main()
