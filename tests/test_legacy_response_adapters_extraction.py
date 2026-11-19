"""Regression coverage for extracted legacy response conversion boundaries."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from declan.core import legacy_response_adapters as adapters
class LegacyResponseAdapterTests(unittest.TestCase):
    def test_routine_triple_uses_live_result_callback(self):
        r = Mock()
        result = SimpleNamespace(reply="done", outcome=SimpleNamespace(value="confirmed"))
        r.run_custom_routine_result.return_value = (result, 200)
        r._routine_legacy_triple.side_effect = lambda typed, status: (typed.reply, typed.outcome.value, status)
        self.assertEqual(adapters.run_custom_routine("morning", approved=True, r=r), ("done", "confirmed", 200))
        r.run_custom_routine_result.assert_called_once_with("morning", None, approved=True, parameters=None)

    def test_routine_execution_forwards_all_options(self):
        r = Mock()
        r.run_routine_result.return_value = ("typed", 202)
        r._routine_legacy_triple.return_value = ("reply", "started", 202)
        self.assertEqual(adapters.run_routine("movie", movie_action="start", movie_room="bedroom", approved=True, r=r), ("reply", "started", 202))
        self.assertEqual(r.run_routine_result.call_args.kwargs["movie_room"], "bedroom")
        r._routine_legacy_triple.assert_called_once_with("typed", 202)

    def test_nullable_switch_preserves_none(self):
        r = Mock()
        r.set_switch_as_light_result.return_value = None
        self.assertIsNone(adapters.set_switch_as_light("fan", "on", {}, None, r=r))



if __name__ == "__main__":
    unittest.main()
