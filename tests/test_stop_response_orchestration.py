"""Stop dispatch and response adaptation regression tests."""

import unittest
from unittest.mock import Mock

from stop_response_orchestration import dispatch_stop_response


class StopResponseOrchestrationTests(unittest.TestCase):
    def test_dispatch_result_is_adapted(self):
        dispatch = Mock(return_value="stopped")
        adapt = Mock(return_value="response")
        args = dict(
            source="assist", origin_device="kitchen", satellite="sat",
            dispatch=dispatch, registry_factory=Mock(), context_factory=Mock(),
            stop_routines=Mock(), stop_everywhere=Mock(), connection=Mock(),
            adapt=adapt,
        )
        self.assertEqual(dispatch_stop_response("stop", **args), "response")
        adapt.assert_called_once_with("stopped")
        self.assertEqual(dispatch.call_args.args, ("stop",))
        self.assertEqual(dispatch.call_args.kwargs["origin_device"], "kitchen")
        self.assertEqual(dispatch.call_args.kwargs["satellite"], "sat")
        self.assertEqual(dispatch.call_args.kwargs["source"], "assist")

    def test_unmatched_stop_does_not_adapt(self):
        adapt = Mock()
        result = dispatch_stop_response(
            "turn on lights", source="chat", origin_device=None,
            satellite=None, dispatch=Mock(return_value=None),
            registry_factory=Mock(), context_factory=Mock(),
            stop_routines=Mock(), stop_everywhere=Mock(),
            connection=Mock(), adapt=adapt,
        )
        self.assertIsNone(result)
        adapt.assert_not_called()


if __name__ == "__main__":
    unittest.main()
