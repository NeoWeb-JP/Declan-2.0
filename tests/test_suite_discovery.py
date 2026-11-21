"""Every tests/test_*.py module must contribute tests to `unittest discover`.

CI runs the suite with unittest, which silently ignores pytest-style module-level
`def test_...` functions. A file written that way would never run in CI.
"""
import unittest
from pathlib import Path

TESTS = Path(__file__).resolve().parent


def _count(suite):
    return sum(_count(t) if isinstance(t, unittest.TestSuite) else 1 for t in suite)


class SuiteDiscoveryTests(unittest.TestCase):
    def test_every_test_module_is_discovered_by_unittest(self):
        loader = unittest.defaultTestLoader
        for path in sorted(TESTS.glob("test_*.py")):
            with self.subTest(module=path.name):
                suite = loader.discover(str(TESTS), pattern=path.name, top_level_dir=str(TESTS))
                self.assertGreater(
                    _count(suite), 0,
                    f"{path.name} has no unittest tests; wrap tests in a unittest.TestCase",
                )


if __name__ == "__main__":
    unittest.main()
