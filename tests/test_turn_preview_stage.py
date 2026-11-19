"""Preview and timer early-result precedence regression tests."""
import unittest
from unittest.mock import patch
from declan.turn import turn_preview_stage


class PreviewStageTests(unittest.TestCase):
    def test_preview_and_timer_selection_delegated_in_order(self):
        kwargs = dict(
            source="assist", origin_device="device", satellite="sat",
            opener=object(), preview_dispatch=object(),
            detect_phrase=object(), preview_routine=object(),
            timer_dispatch=object(), registry_factory=object(),
            context_factory=object(), matches=object(), handle=object(),
            guest_mode=object(), decorate=object(),
        )
        sentinel = object()
        with patch.object(turn_preview_stage.preview_timer_orchestration, "preview_and_timer", return_value=("preview", "timer")) as dispatch, patch.object(
            turn_preview_stage.preview_timer_orchestration, "select_early_result", return_value=sentinel,
        ) as select:
            result = turn_preview_stage.resolve("test", **kwargs)
        self.assertIs(result, sentinel)
        self.assertEqual(dispatch.call_args.args, ("test",))
        select.assert_called_once_with("preview", "timer")

    def test_no_early_result_allows_later_dispatch(self):
        kwargs = dict(
            source="assist", origin_device=None, satellite=None,
            opener=None, preview_dispatch=None, detect_phrase=None,
            preview_routine=None, timer_dispatch=None,
            registry_factory=None, context_factory=None, matches=None,
            handle=None, guest_mode=None, decorate=None,
        )
        with patch.object(turn_preview_stage.preview_timer_orchestration, "preview_and_timer", return_value=(None, None)), patch.object(
            turn_preview_stage.preview_timer_orchestration, "select_early_result", return_value=None,
        ):
            self.assertIsNone(turn_preview_stage.resolve("ordinary request", **kwargs))


if __name__ == "__main__":
    unittest.main()
