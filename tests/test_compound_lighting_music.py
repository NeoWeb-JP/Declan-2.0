"""#300: one lighting command joined to one music command runs as two independent actions."""
import unittest
from unittest import mock

import server
from declan.core.execution_results import ExecutionResult, Outcome
from declan.ha import lighting_intents
from declan.music import music
from declan.turn import compound_commands, turn_dispatch_orchestration


def split(phrase):
    return compound_commands.split_lighting_and_music(
        phrase, parse_music=music.parse,
        is_lighting=lambda text: lighting_intents.matches(text, server.parse_light_command),
    )


class SplitterTests(unittest.TestCase):
    def test_both_orders_split_without_contaminating_targets(self):
        cases = {
            "turn on the office lights and play country music everywhere":
                ("turn on the office lights", "play country music everywhere"),
            "play country music everywhere and turn on the office light":
                ("play country music everywhere", "turn on the office light"),
            "turn off the kitchen lights and then play rock in the lounge":
                ("turn off the kitchen lights", "play rock in the lounge"),
            "play rock in the lounge, and turn on the office light":
                ("play rock in the lounge", "turn on the office light"),
        }
        for phrase, expected in cases.items():
            with self.subTest(phrase=phrase):
                result = split(phrase)
                self.assertIsNotNone(result)
                self.assertEqual((result.first, result.second), expected)
        halves = split("play country music everywhere and turn on the office light")
        self.assertEqual(music.parse(halves.first)[0], "everywhere")
        self.assertEqual(server.parse_light_command(halves.second), ("office light", "on"))

    def test_conjunctions_inside_one_command_stay_whole(self):
        for phrase in (
            "turn on the kitchen and dining lights",
            "play rock in the kitchen and lounge",
            "turn on the office lights",
            "play country music everywhere",
            "turn on the lights and turn off the fan",
            "play rock and play jazz",
        ):
            with self.subTest(phrase=phrase):
                self.assertIsNone(split(phrase))

    def test_context_dependent_lighting_is_not_split(self):
        for phrase in ("play rock everywhere and turn them on",
                       "play rock everywhere and turn it off",
                       "preview turn on the office lights and play rock everywhere"):
            with self.subTest(phrase=phrase):
                self.assertIsNone(split(phrase))

    def test_parser_errors_and_oversized_input_keep_the_phrase_whole(self):
        def broken(_text):
            raise ValueError("bad")
        self.assertIsNone(compound_commands.split_lighting_and_music(
            "turn on the office lights and play rock", parse_music=broken, is_lighting=lambda _t: True))
        self.assertIsNone(split("play rock and turn on the office light " + "x" * 600))
        self.assertIsNone(split(None))


class OutcomeTests(unittest.TestCase):
    def test_failure_is_never_hidden_behind_success(self):
        combine = compound_commands.combined_outcome
        self.assertIs(combine(Outcome.CONFIRMED, Outcome.CONFIRMED), Outcome.CONFIRMED)
        self.assertIs(combine(Outcome.CONFIRMED, Outcome.FAILED), Outcome.PARTIAL)
        self.assertIs(combine(Outcome.UNAVAILABLE, Outcome.CONFIRMED), Outcome.PARTIAL)
        self.assertIs(combine(Outcome.CONFIRMED, Outcome.REQUESTED), Outcome.REQUESTED)
        self.assertIs(combine(Outcome.STARTED, Outcome.CONFIRMED), Outcome.STARTED)
        self.assertIs(combine(Outcome.FAILED, Outcome.UNVERIFIED), Outcome.UNVERIFIED)
        self.assertIs(combine(Outcome.FAILED, Outcome.FAILED), Outcome.FAILED)
        self.assertIs(combine(Outcome.FAILED, Outcome.UNAVAILABLE), Outcome.FAILED)
        self.assertIs(combine(Outcome.CONFIRMED, None), Outcome.PARTIAL)
        self.assertIsNone(combine(None, None))


class CompoundDispatchTests(unittest.TestCase):
    def run_turn(self, phrase, *, light, play):
        calls = []

        def fake_light(text, *, action_results=None, last_lights=(), origin_device=None):
            calls.append(("light", text))
            return light

        def fake_play(command, connection, read_inventory, *, origin=None):
            calls.append(("music", command[0], command[1]))
            return play

        with mock.patch.object(server, "handle_light_request_result", fake_light), \
                mock.patch.object(music, "play_result", fake_play), \
                mock.patch.object(server, "ha_device_connection", lambda: object()), \
                mock.patch.object(server, "select_routine_turn_result", lambda *a, **k: None), \
                mock.patch.object(server, "read_guest_mode", lambda *a, **k: "off"):
            result = turn_dispatch_orchestration.dispatch(
                phrase, source="assist", origin_device=None, satellite=None,
                action_results=server.ActionEvidenceBuffer(), scope=None, last_lights=(),
                last_device=None, last_information=None, services=server._turn_services(),
            )
        return result, calls

    def test_lighting_first_runs_both_with_clean_targets(self):
        result, calls = self.run_turn(
            "turn on the office lights and play country music everywhere",
            light=ExecutionResult("Office lights are on.", Outcome.CONFIRMED),
            play=ExecutionResult("Country is playing everywhere.", Outcome.CONFIRMED))
        self.assertEqual(calls, [("light", "turn on the office lights"),
                                 ("music", "everywhere", "country music")])
        self.assertEqual(result.reply, "Office lights are on. Country is playing everywhere.")
        self.assertIs(result.outcome, Outcome.CONFIRMED)

    def test_music_first_no_longer_treats_the_lighting_command_as_a_player(self):
        result, calls = self.run_turn(
            "play country music everywhere and turn on the office light",
            light=ExecutionResult("Office light is on.", Outcome.CONFIRMED),
            play=ExecutionResult("Country is playing everywhere.", Outcome.CONFIRMED))
        self.assertEqual(calls, [("music", "everywhere", "country music"),
                                 ("light", "turn on the office light")])
        self.assertNotIn("everywhere and turn", result.reply)
        self.assertIs(result.outcome, Outcome.CONFIRMED)

    def test_one_failure_does_not_stop_the_other_and_is_reported(self):
        result, calls = self.run_turn(
            "play country music everywhere and turn on the office light",
            light=ExecutionResult("I couldn't confirm the office light.", Outcome.UNVERIFIED),
            play=ExecutionResult("Country is playing everywhere.", Outcome.CONFIRMED))
        self.assertEqual(len(calls), 2)
        self.assertIs(result.outcome, Outcome.PARTIAL)
        self.assertIn("couldn't confirm the office light", result.reply)
        self.assertIn("Country is playing", result.reply)

        result, calls = self.run_turn(
            "turn on the office lights and play country music everywhere",
            light=ExecutionResult("Office lights are on.", Outcome.CONFIRMED),
            play=ExecutionResult("Spotify is rate limited; I haven't changed playback.", Outcome.UNAVAILABLE))
        self.assertEqual(len(calls), 2)
        self.assertIs(result.outcome, Outcome.PARTIAL)
        self.assertIn("haven't changed playback", result.reply)

    def test_single_commands_are_dispatched_unchanged(self):
        result, calls = self.run_turn(
            "turn on the kitchen and dining lights",
            light=ExecutionResult("Done.", Outcome.CONFIRMED),
            play=ExecutionResult("unused", Outcome.CONFIRMED))
        self.assertEqual(calls, [("light", "turn on the kitchen and dining lights")])


if __name__ == "__main__":
    unittest.main()
