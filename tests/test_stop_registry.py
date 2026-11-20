"""Stop command dispatch and failure ownership regression tests."""
from result_pairs import pair
from unittest import TestCase
from unittest.mock import Mock

from declan.turn.command_registry import RequestContext, stop_registry
from declan.core.execution_results import Outcome


class StopRegistryTests(TestCase):
    def setUp(self):
        self.stop_routines = Mock(return_value=("Routine cancellation requested.", "unverified", "pending"))
        self.stop_everywhere = Mock(return_value=("Stopped.", "confirmed", None))
        self.connection = Mock(return_value="HA")
        self.registry = stop_registry(stop_routines=self.stop_routines,
                                      stop_everywhere=self.stop_everywhere, connection=self.connection)

    def dispatch(self, phrase):
        return self.registry.dispatch(RequestContext(phrase=phrase, source="assist"))

    def test_routine_variants_keep_status(self):
        for phrase in ("stop routine", "cancel routine", "stop the routine", "cancel the routine"):
            result = self.dispatch(phrase)
            self.assertEqual(result.handler, "stop_routine")
            self.assertIs(result.result.outcome, Outcome.UNVERIFIED)
            self.assertEqual(result.routine_status, "pending")
        self.stop_everywhere.assert_not_called()
        self.connection.assert_not_called()

    def test_plain_stop_uses_home_assistant(self):
        result = self.dispatch("stop")
        self.assertEqual(result.handler, "stop_everywhere")
        self.assertEqual(pair(result.result), ("Stopped.", "confirmed"))
        self.stop_everywhere.assert_called_once_with("HA")
        self.stop_routines.assert_not_called()

    def test_non_stop_has_no_side_effects(self):
        self.assertIsNone(self.dispatch("stop the kitchen timer"))
        self.stop_routines.assert_not_called()
        self.stop_everywhere.assert_not_called()
        self.connection.assert_not_called()

    def test_failure_does_not_fall_through(self):
        self.stop_routines.side_effect = OSError("connection lost")
        with self.assertRaises(OSError):
            self.dispatch("stop routine")
        self.stop_everywhere.assert_not_called()
