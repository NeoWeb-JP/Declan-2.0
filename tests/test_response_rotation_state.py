"""Bounded response rotation, concurrency and tone isolation regressions."""

from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch

from declan.turn import personality
from declan.turn import personality_policy
from declan.turn.response_rotation_state import ResponseRotationState


class FirstChoice:
    def choice(self, values):
        return values[0]


class ResponseRotationTests(unittest.TestCase):
    def test_two_lines_remain_available_when_recent_window_exhausts(self):
        state = ResponseRotationState(window=3, random=FirstChoice())
        result = [state.choose(("home", "small"), ("first", "second")) for _ in range(8)]
        self.assertEqual(result[:3], ["first", "second", "first"])
        self.assertEqual(set(result), {"first", "second"})

    def test_empty_selection_returns_empty_string(self):
        state = ResponseRotationState()
        self.assertEqual(state.choose("empty", []), "")

    def test_home_and_guest_recent_choices_are_independent(self):
        state = ResponseRotationState(window=2, random=FirstChoice())
        self.assertEqual(state.choose(("home", "morning"), ("one", "two", "three")), "one")
        self.assertEqual(state.choose(("guest", "morning"), ("one", "two", "three")), "one")
        self.assertEqual(state.choose(("home", "morning"), ("one", "two", "three")), "two")

    def test_concurrent_selection_is_bounded(self):
        state = ResponseRotationState(window=3)
        with ThreadPoolExecutor(max_workers=8) as pool:
            values = list(pool.map(lambda _: state.choose("music", ("a", "b", "c", "d")),
                                   range(200)))
        self.assertEqual(len(values), 200)
        self.assertTrue(set(values) <= {"a", "b", "c", "d"})
        self.assertEqual(len(state.recent["music"]), 3)

    def test_state_instances_do_not_share_recent_responses(self):
        first = ResponseRotationState(random=FirstChoice())
        second = ResponseRotationState(random=FirstChoice())
        first.choose("music", ("a", "b"))
        self.assertNotIn("music", second.recent)

    def test_builtin_personality_exhausted_category_does_not_raise(self):
        state = ResponseRotationState(window=2, random=FirstChoice())
        with patch.object(personality, "ROTATION", state), \
             patch.object(personality.command_responses if hasattr(personality, "command_responses")
                          else __import__("declan.turn.command_responses", fromlist=["selected"]), "selected", return_value=None), \
             patch.dict(personality.LINES, {"test_short": (("one", "two"), ("quiet",))}):
            results = [personality.choose_line("test_short", "off") for _ in range(6)]
            self.assertEqual(set(results), {"one", "two"})
            self.assertEqual(personality.choose_line("test_short", "on"), "quiet")

    def test_policy_home_and_guest_outputs_stay_independent(self):
        state = ResponseRotationState(window=3, random=FirstChoice())
        with patch.object(personality_policy, "ROTATION", state):
            home = personality_policy.morning_request_reply(visitor_present=False)
            guest = personality_policy.morning_request_reply(guest=True)
            self.assertTrue(home.startswith("Good morning. "))
            self.assertTrue(guest.startswith("Good morning. "))
            self.assertEqual(set(state.recent), {("home", "morning"), ("guest", "morning")})


if __name__ == "__main__":
    unittest.main()
