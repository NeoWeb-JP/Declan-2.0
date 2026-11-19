"""Chained routine action and response regression tests."""
import unittest
from unittest.mock import Mock
from declan.turn import routine_follow_on


class RoutineFollowOnTests(unittest.TestCase):
    def setUp(self):
        self.actions = []
        self.parse = Mock(return_value={"genre": "country"})
        self.play = Mock(return_value=("Playing country.", "confirmed"))
        self.lighting = Mock(return_value=("Kitchen lights off.", "confirmed"))
        self.connection = Mock(return_value="connection")
        self.inventory = Mock()
        self.combine = Mock(side_effect=lambda a, b: "confirmed" if a == b == "confirmed" else "partial")

    def run_follow_on(self, phrase, *, scope="kitchen", status="Routine finished.", music_origin="bedroom"):
        return routine_follow_on.execute(
            phrase, routine_reply="Routine started.", routine_outcome="confirmed",
            routine_status=status, parse_music=self.parse, play_music=self.play,
            connection=self.connection, music_inventory=self.inventory,
            handle_lighting=self.lighting, last_lights=("kitchen",), origin="kitchen",
            music_origin=music_origin, action_results=self.actions, scope=scope,
            chained_outcome=self.combine)

    def test_music_uses_origin_without_lighting(self):
        result = self.run_follow_on("play country")
        self.assertEqual(result.reply, "Routine started. Routine finished. Playing country.")
        self.assertEqual(result.routine_voice_result, ("Routine started.", "confirmed"))
        self.assertEqual(result.lighting_context, ())
        self.play.assert_called_once_with({"genre": "country"}, "connection", self.inventory, origin="bedroom")
        self.lighting.assert_not_called()

    def test_lighting_records_actions_and_context(self):
        self.lighting.side_effect = lambda phrase, **kw: (kw["action_results"].append(
            {"entity_id": "light.kitchen", "status": "confirmed"}), ("Kitchen lights off.", "confirmed"))[1]
        result = self.run_follow_on("turn off kitchen")
        self.assertEqual(result.lighting_context, ("light.kitchen",))
        self.assertEqual(self.actions, [{"entity_id": "light.kitchen", "status": "confirmed"}])
        self.play.assert_not_called()

    def test_missing_music_command_is_unresolved(self):
        self.parse.return_value = None
        result = self.run_follow_on("play nonsense")
        self.assertIn("Tell me where to play the music.", result.reply)
        self.play.assert_not_called()
        self.combine.assert_called_once_with("confirmed", "unresolved")

    def test_unmatched_lighting_is_unresolved(self):
        self.lighting.return_value = None
        result = self.run_follow_on("turn off mystery")
        self.assertIn("couldn't understand the lighting command", result.reply)
        self.combine.assert_called_once_with("confirmed", "unresolved")

    def test_status_not_duplicated_and_no_scope_context(self):
        self.lighting.side_effect = lambda phrase, **kw: (kw["action_results"].append(
            {"entity_id": "light.kitchen", "status": "confirmed"}), ("Done.", "confirmed"))[1]
        result = self.run_follow_on("turn off kitchen", scope=None, status="Routine started.")
        self.assertEqual(result.reply, "Routine started. Done.")
        self.assertEqual(result.lighting_context, ())
