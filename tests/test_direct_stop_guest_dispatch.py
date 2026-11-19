"""Guard direct stop/guest ordering across extracted turn stages."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SERVER = (ROOT / "server.py").read_text()
DIRECT = (ROOT / "turn_direct_dispatch.py").read_text()
DISPATCH = (ROOT / "turn_dispatch_orchestration.py").read_text()


class DirectCommandDispatchTests(unittest.TestCase):
    def test_stop_result_adapted_before_response(self):
        dispatch = DIRECT.index("stop_command_dispatch.dispatch_stop(")
        adapt = DIRECT.index("stop_result_response.stop_response(stop)", dispatch)
        response = DIRECT.index("reply=response.result.reply", adapt)
        self.assertLess(dispatch, adapt)
        self.assertLess(adapt, response)
        self.assertIn("routine_reply, outcome = direct_result.reply, direct_result.outcome", DISPATCH)

    def test_guest_dispatch_preserves_confirmation_and_order(self):
        confirmation = SERVER.index("turn_preflight_entry.resolve(")
        self.assertIn("turn_preflight.resolve(", (ROOT / "turn_preflight_entry.py").read_text())
        preflight_source = (ROOT / "turn_preflight.py").read_text()
        self.assertIn("sensitive_confirmation_resolution.resolve_confirmation(", preflight_source)
        direct = DISPATCH.index("turn_direct_dispatch.dispatch(")
        stop = DIRECT.index("stop_command_dispatch.dispatch_stop(")
        guest = DIRECT.index("roast_guest_dispatch.dispatch_roast_or_guest_result(", stop)
        self.assertIn("turn_dispatch_orchestration.dispatch(", SERVER)
        self.assertGreaterEqual(confirmation, 0)
        self.assertGreaterEqual(direct, 0)
        self.assertLess(stop, guest)
        self.assertIn("guest_commands=GUEST_COMMANDS", DISPATCH)
        self.assertIn("connection=ha_device_connection", DISPATCH)


if __name__ == "__main__":
    unittest.main()
