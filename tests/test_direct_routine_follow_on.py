"""Direct routine follow-on typed response contract."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SERVER = (ROOT / "server.py").read_text()
STAGE = (ROOT / "turn_routine_stage.py").read_text()


class DirectRoutineFollowOnTests(unittest.TestCase):
    def test_typed_follow_on_result_preserves_response_and_context(self):
        start = STAGE.index("follow_on = routine_follow_on_dispatch.execute_follow_on_result(")
        reply = STAGE.index("reply=follow_on.result.reply", start)
        lights = STAGE.index("lighting_context=follow_on.lighting_context", reply)
        voice = STAGE.index("routine_voice_result=follow_on.routine_voice_result", lights)
        self.assertLess(start, reply)
        self.assertLess(reply, lights)
        self.assertLess(lights, voice)
        self.assertIn("routine_reply, outcome = routine_result.reply, routine_result.outcome", SERVER)

    def test_music_and_lighting_follow_on_dependencies_preserved(self):
        start = SERVER.index("turn_routine_stage.dispatch(")
        end = SERVER.index("routine_status = routine_result.routine_status", start)
        call = SERVER[start:end]
        for dependency in (
            "follow_on_execute=routine_follow_on.execute_result",
            "parse_music=music.parse",
            "play_music=music.play_result",
            "handle_lighting=handle_light_request_result",
            "action_results=action_results",
            "chained_outcome=chained_outcome_result",
        ):
            with self.subTest(dependency=dependency):
                self.assertIn(dependency, call)
        self.assertIn("routine_follow_on_dispatch.execute_follow_on_result(", STAGE)


if __name__ == "__main__":
    unittest.main()
