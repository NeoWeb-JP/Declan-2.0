"""Direct routine and information dispatch contract."""
from pathlib import Path
import unittest

SERVER = (Path(__file__).resolve().parents[1] / "server.py").read_text()


class DirectRoutineInformationTests(unittest.TestCase):
    def test_routine_dispatch_precedes_information_fallback(self):
        routine = SERVER.index("routine_registry_dispatch.dispatch_routine(")
        follow_on = SERVER.index("routine_follow_on_dispatch.execute_follow_on_result(", routine)
        information = SERVER.index("information_command_dispatch.dispatch_information(", follow_on)
        self.assertLess(routine, follow_on)
        self.assertLess(follow_on, information)
        self.assertIn("select=select_routine_turn_result", SERVER)
        self.assertIn("execute=execute_routine_result", SERVER)

    def test_information_response_adapted_only_when_handled(self):
        dispatch = SERVER.index("information_dispatch = information_command_dispatch.dispatch_information(")
        guard = SERVER.index("if information_dispatch:", dispatch)
        adapt = SERVER.index("information_result_response.information_response(information_dispatch)", guard)
        device = SERVER.index("device_command_dispatch.dispatch_device(", adapt)
        self.assertLess(dispatch, guard)
        self.assertLess(guard, adapt)
        self.assertLess(adapt, device)


if __name__ == "__main__":
    unittest.main()
