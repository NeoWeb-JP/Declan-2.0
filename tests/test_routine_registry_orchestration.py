"""Routine registry dispatch regression tests."""

import unittest
from unittest.mock import Mock

from routine_registry_orchestration import dispatch_routine


class RoutineRegistryOrchestrationTests(unittest.TestCase):
    def test_forwards_dispatch_context_and_action_evidence(self):
        dispatch = Mock(return_value="routine")
        dependencies = {
            "registry_factory": Mock(), "context_factory": Mock(),
            "select": Mock(), "execute": Mock(),
        }
        result = dispatch_routine(
            "good night", source="assist", origin_device="bedroom",
            satellite="satellite", action_results="actions",
            dispatch=dispatch, **dependencies,
        )
        self.assertEqual(result, "routine")
        dispatch.assert_called_once_with(
            "good night", source="assist", origin_device="bedroom",
            satellite="satellite", action_results="actions", **dependencies,
        )

    def test_unmatched_routine_falls_through(self):
        dispatch = Mock(return_value=None)
        self.assertIsNone(dispatch_routine(
            "what time is it", source="chat", origin_device=None,
            satellite=None, action_results=None, dispatch=dispatch,
            registry_factory=Mock(), context_factory=Mock(),
            select=Mock(), execute=Mock(),
        ))


if __name__ == "__main__":
    unittest.main()
