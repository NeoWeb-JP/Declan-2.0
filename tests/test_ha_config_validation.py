"""Check HA setup URL validation without requiring Home Assistant imports."""
import importlib.util
from pathlib import Path
import unittest


PATH = Path(__file__).resolve().parents[1] / "custom_components/declan_two/config_validation.py"
SPEC = importlib.util.spec_from_file_location("declan_config_validation", PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ConfigValidationTests(unittest.TestCase):
    def test_accepts_origins(self):
        for url in ("http://localhost:52737", "https://declan.example.com", "http://127.0.0.1:52737/"):
            with self.subTest(url=url):
                self.assertTrue(MODULE.valid_declan_origin(url))

    def test_rejects_non_origins_and_unsafe_urls(self):
        for url in (
            "ftp://declan.example.com", "http://", "http://declan.example.com/api",
            "http://declan.example.com/?token=secret", "https://user:pass@declan.example.com",
            "http://declan.example.com/#fragment", "http://declan.example.com:0",
            "http://declan.example.com:bad", "https://[broken",
        ):
            with self.subTest(url=url):
                self.assertFalse(MODULE.valid_declan_origin(url))


if __name__ == "__main__":
    unittest.main()
