"""FUT-60: Sexy Time only affects the room it was started in."""
import unittest
from pathlib import Path
from types import SimpleNamespace

from declan.ha import script_discovery
from declan.turn import routine_request_selection
from declan.turn.routine_selection_results import RoutineSelectionKind

ROOT = Path(__file__).resolve().parents[1]
SEXY = {"sexy time": "start", "end sexy time": "end"}


def select(phrase, origin, fields):
    item = {"entity_id": "script.declan_sexy_time_controller", "name": "Declan - Sexy Time Controller",
            "fields": fields}
    matched = SimpleNamespace(status=script_discovery.ScriptMatchStatus.MATCHED, selected=item)
    missing = SimpleNamespace(status=script_discovery.ScriptMatchStatus.NO_MATCH, selected=None)
    discovery = SimpleNamespace(
        discover_result=lambda connection: SimpleNamespace(error=None, scripts=[item]),
        match_result=lambda candidate, scripts: matched if candidate == "sexy time" else missing,
        phrases=script_discovery.phrases, ScriptMatchStatus=script_discovery.ScriptMatchStatus)
    return routine_request_selection.select_routine_result(
        phrase, origin, connect=lambda: ("http://ha", {}, None), discovery_module=discovery,
        movie_parser=lambda phrase: None, morning_phrases=set(), night_phrases=set(),
        dinner_phrases=set(), sexy_commands=SEXY)


class SexyTimeRoomTests(unittest.TestCase):
    def test_origin_is_sent_with_the_operation(self):
        result = select("sexy time", "assist_satellite.guest_room", ["operation", "origin"])
        assert result is not None
        self.assertEqual(result.kind, RoutineSelectionKind.SCRIPT)
        self.assertEqual(result.options["origin"], "assist_satellite.guest_room")
        self.assertEqual(result.options["operation"], "start")
        ended = select("end sexy time", "device-123", ["operation", "origin"])
        assert ended is not None
        self.assertEqual((ended.options["operation"], ended.options["origin"]), ("end", "device-123"))

    def test_no_origin_leaves_the_script_default(self):
        for origin in (None, "", "  "):
            result = select("sexy time", origin, ["operation", "origin"])
            assert result is not None
            self.assertNotIn("origin", result.options)

    def test_example_script_resolves_the_room_and_restores_other_rooms(self):
        # CI has no YAML parser; check the field and the room logic in the text.
        text = (ROOT / "home_assistant/sexy_time.script.yaml").read_text()
        self.assertIn("\n  origin:\n    name:", text.split("sequence:", 1)[0])
        for needle in ("area_name(source)", "area_entities(room)", "scene.create", "snapshot_entities",
                       "scene.turn_on", "'Master Bedroom'", "room: \"{{ room }}\""):
            self.assertIn(needle, text)

    def test_master_bedroom_includes_the_spotlight_mood_zone(self):
        text = (ROOT / "home_assistant/sexy_time.script.yaml").read_text()
        start, _, end = text.partition("            default:")
        for needle in ("light.bedroom_mood_lights", "scene.create", "declan_mood_bedroom_spotlights",
                       "continue_on_error: true"):
            self.assertIn(needle, start)
        self.assertIn("scene.declan_mood_bedroom_spotlights", end)
        # Slow cloud lights never decide whether Sexy Time counts as started.
        self.assertNotIn("bedroom_mood_lights", text.split("lighting_ok:", 1)[1])


if __name__ == "__main__":
    unittest.main()
