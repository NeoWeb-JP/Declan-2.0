"""Typed turn persistence boundary regressions."""
import unittest
from unittest.mock import Mock

from turn_persistence_orchestration import persist_turn_result


class TypedPersistenceTests(unittest.TestCase):
    def test_rejects_untyped_response_without_persisting(self):
        finalize = Mock()
        with self.assertRaisesRegex(ValueError, "typed turn response"):
            persist_turn_result({"session_id": "abc"}, finalize=finalize)
        finalize.assert_not_called()


if __name__ == "__main__":
    unittest.main()
