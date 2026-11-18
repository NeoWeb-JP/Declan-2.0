"""Protect direct device dispatch and response adaptation."""
from pathlib import Path
import unittest

SERVER = (Path(__file__).resolve().parents[1] / "server.py").read_text()


class DirectDeviceDispatchTests(unittest.TestCase):
    def test_device_dispatch_and_adaptation_before_lighting_fallback(self):
        dispatch = SERVER.index("device_dispatch = device_command_dispatch.dispatch_device(")
        guard = SERVER.index("if device_dispatch is not None:", dispatch)
        adapt = SERVER.index("device_result_response.device_response(device_dispatch)", guard)
        status = SERVER.index("status_target = device_response.status_target", adapt)
        lighting = SERVER.index("lighting_result_dispatch.dispatch_lighting_response(", status)
        self.assertLess(dispatch, guard)
        self.assertLess(guard, adapt)
        self.assertLess(adapt, status)
        self.assertLess(status, lighting)

    def test_music_and_device_context_dependencies_remain(self):
        for dependency in (
            "last_device=last_device",
            "origin_device=origin_device",
            "satellite=satellite",
            "parse_music=music.parse",
            "play=music.play_result",
            "search_media=search_media_result",
        ):
            with self.subTest(dependency=dependency):
                self.assertIn(dependency, SERVER)


if __name__ == "__main__":
    unittest.main()
