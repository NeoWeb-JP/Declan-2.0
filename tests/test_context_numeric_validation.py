"""Shared session timing validation regression tests."""

import unittest

from context_numeric_validation import finite_number


class FiniteNumberTests(unittest.TestCase):
    def test_valid_finite_timing_values(self):
        for value in (0, -1, 1, 1.5, -0.5, 10 ** 100):
            with self.subTest(value=value):
                self.assertTrue(finite_number(value))

    def test_invalid_timing_values(self):
        for value in (None, True, False, "10", [], {}, float("nan"),
                      float("inf"), float("-inf"), 10 ** 1000):
            with self.subTest(type=type(value).__name__):
                self.assertFalse(finite_number(value))


if __name__ == "__main__":
    unittest.main()
