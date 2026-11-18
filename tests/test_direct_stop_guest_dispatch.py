"""Guard direct stop and guest dispatch after orchestration cleanup."""
from pathlib import Path
import unittest

SERVER = (Path(__file__).resolve().parents[1] / "server.py").read_text()


class DirectCommandDispatchTests(unittest.TestCase):
    def test_stop_result_adapted_before_response(self):
        dispatch = SERVER.index("elif stop_dispatch := stop_command_dispatch.dispatch_stop(")
        adapt = SERVER.index("stop_result_response.stop_response(stop_dispatch)", dispatch)
        response = SERVER.index("routine_reply, outcome = stop_response.result.reply", adapt)
        self.assertLess(dispatch, adapt)
        self.assertLess(adapt, response)

    def test_guest_dispatch_preserves_confirmation_and_order(self):
        confirmation = SERVER.index("turn_preflight.resolve(")
        preflight_source = (Path(__file__).resolve().parents[1] / "turn_preflight.py").read_text()
        self.assertIn("sensitive_confirmation_resolution.resolve_confirmation(", preflight_source)
        stop = SERVER.index("stop_command_dispatch.dispatch_stop(", confirmation)
        guest = SERVER.index("roast_guest_dispatch.dispatch_roast_or_guest_result(", stop)
        self.assertLess(confirmation, stop)
        self.assertLess(stop, guest)
        self.assertIn("guest_commands=GUEST_COMMANDS", SERVER)
        self.assertIn("connection=ha_device_connection", SERVER)


if __name__ == "__main__":
    unittest.main()
