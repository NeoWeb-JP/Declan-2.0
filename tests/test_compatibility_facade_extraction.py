"""Compatibility facade regression tests."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from declan.core import compatibility_facade as facade
class CompatibilityFacadeTests(unittest.TestCase):
    def test_routine_outcome_preserves_triple(self):
        r = Mock()
        outcome = SimpleNamespace(reply="done", outcome=SimpleNamespace(value="confirmed"))
        self.assertEqual(facade._routine_legacy_triple(outcome, 200, r=r), ("done", "confirmed", 200))

    def test_routine_selection_preserves_none(self):
        r = Mock()
        r.select_routine_result.return_value = None
        self.assertIsNone(facade.select_routine("hello", "kitchen", r=r))




if __name__ == "__main__":
    unittest.main()
