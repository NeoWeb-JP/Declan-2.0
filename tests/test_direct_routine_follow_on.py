"""Direct routine follow-on typed response contract."""
from pathlib import Path
import unittest

SERVER = (Path(__file__).resolve().parents[1] / "server.py").read_text()


class DirectRoutineFollowOnTests(unittest.TestCase):
    def test_typed_follow_on_result_preserves_response_and_context(self):
        start = SERVER.index("follow_on = routine_follow_on_dispatch.execute_follow_on_result(")
        reply = SERVER.index("routine_reply, outcome = follow_on.result.reply, follow_on.result.outcome", start)
        lights = SERVER.index("lighting_context = follow_on.lighting_context", reply)
        voice = SERVER.index("routine_voice_result = follow_on.routine_voice_result", lights)
        self.assertLess(start, reply)
        self.assertLess(reply, lights)
        self.assertLess(lights, voice)

    def test_music_and_lighting_follow_on_dependencies_preserved(self):
        start = SERVER.index("follow_on = routine_follow_on_dispatch.execute_follow_on_result(")
        end = SERVER.index("routine_reply, outcome = follow_on.result.reply", start)
        call = SERVER[start:end]
        for dependency in (
            "execute=routine_follow_on.execute_result",
            "parse_music=music.parse",
            "play_music=music.play_result",
            "handle_lighting=handle_light_request_result",
            "action_results=action_results",
            "chained_outcome=chained_outcome_result",
        ):
            with self.subTest(dependency=dependency):
                self.assertIn(dependency, call)


if __name__ == "__main__":
    unittest.main()
