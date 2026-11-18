"""Preview-first timer orchestration regressions."""

import unittest
from unittest.mock import Mock

from preview_timer_orchestration import preview_and_timer


class PreviewTimerOrchestrationTests(unittest.TestCase):
    def test_preview_is_passed_to_timer_in_order(self):
        calls = []
        def preview(*args, **kwargs):
            calls.append(("preview", args, kwargs))
            return "preview-result"
        def timer(*args, **kwargs):
            calls.append(("timer", args, kwargs))
            return "timer-result"
        dependencies = {
            "preview_dispatch": preview, "detect_phrase": Mock(),
            "preview_routine": Mock(), "timer_dispatch": timer,
            "registry_factory": Mock(), "context_factory": Mock(),
            "matches": Mock(), "handle": Mock(), "guest_mode": Mock(),
            "decorate": Mock(),
        }
        result = preview_and_timer(
            "set timer", source="assist", origin_device="kitchen",
            satellite="satellite", opener="opener", **dependencies,
        )
        self.assertEqual(result, ("preview-result", "timer-result"))
        self.assertEqual([entry[0] for entry in calls], ["preview", "timer"])
        self.assertEqual(calls[1][2]["routine_preview"], "preview-result")
        self.assertEqual(calls[1][2]["origin_device"], "kitchen")
        self.assertEqual(calls[1][2]["satellite"], "satellite")
        self.assertEqual(calls[1][2]["source"], "assist")
        self.assertEqual(calls[1][2]["opener"], "opener")

    def test_no_preview_still_dispatches_timer(self):
        timer = Mock(return_value=None)
        result = preview_and_timer(
            "five minutes", source="chat", origin_device=None,
            satellite=None, opener=None,
            preview_dispatch=Mock(return_value=None),
            detect_phrase=Mock(), preview_routine=Mock(),
            timer_dispatch=timer, registry_factory=Mock(),
            context_factory=Mock(), matches=Mock(), handle=Mock(),
            guest_mode=Mock(), decorate=Mock(),
        )
        self.assertEqual(result, (None, None))
        self.assertIsNone(timer.call_args.kwargs["routine_preview"])


if __name__ == "__main__":
    unittest.main()
