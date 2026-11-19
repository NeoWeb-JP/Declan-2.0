"""Direct routine and information dispatch contract."""
from pathlib import Path
import unittest

DISPATCH = (Path(__file__).resolve().parents[1] / "declan/turn/turn_dispatch_orchestration.py").read_text()
FALLBACK = (Path(__file__).resolve().parents[1] / "declan/turn/turn_fallback_dispatch.py").read_text()


class DirectRoutineInformationTests(unittest.TestCase):
    def test_routine_dispatch_precedes_information_fallback(self):
        routine = DISPATCH.index("turn_routine_stage.dispatch(")
        information = DISPATCH.index("turn_fallback_dispatch.dispatch(", routine)
        self.assertLess(routine, information)
        stage = (Path(__file__).resolve().parents[1] / "declan/turn/turn_routine_stage.py").read_text()
        selection = stage.index("routine_registry_dispatch.dispatch_routine(")
        follow_on = stage.index("routine_follow_on_dispatch.execute_follow_on_result(", selection)
        self.assertLess(selection, follow_on)
        self.assertIn("select=select_routine_turn_result", DISPATCH)
        self.assertIn("execute=execute_routine_result", DISPATCH)

    def test_information_response_adapted_only_when_handled(self):
        dispatch = FALLBACK.index("information_dispatch = information_command_dispatch.dispatch_information(")
        guard = FALLBACK.index("if information_dispatch:", dispatch)
        adapt = FALLBACK.index("information_result_response.information_response(information_dispatch)", guard)
        device = FALLBACK.index("device_command_dispatch.dispatch_device(", adapt)
        self.assertLess(dispatch, guard)
        self.assertLess(guard, adapt)
        self.assertLess(adapt, device)


if __name__ == "__main__":
    unittest.main()
