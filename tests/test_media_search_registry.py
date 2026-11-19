"""Media-search priority registry regressions (issue #17)."""
from dataclasses import replace
from unittest import TestCase
from unittest.mock import Mock

from declan.turn import command_registry as commands
from execution_results import Outcome
def dependencies():
    return commands.Dependencies(
        parse_status=Mock(return_value=None), describe_status=Mock(),
        connection=Mock(return_value="connection"), inventory=Mock(),
        decorate=Mock(), guest_mode_entity="input_boolean.guest_mode",
        parse_feedback=Mock(return_value=None), feedback=Mock(),
        parse_control=Mock(return_value=None), control=Mock(),
        parse_music=Mock(return_value=None), play=Mock(return_value=("Playing.", "confirmed")),
        music_inventory=Mock(), areas=Mock(),
    )


class MediaSearchRegistryTests(TestCase):
    def setUp(self):
        self.search = Mock(return_value=("Found on streaming.", "search_result"))
        self.deps = replace(dependencies(), search_media=self.search)

    def dispatch(self, phrase):
        return commands.registry(self.deps).dispatch(commands.RequestContext(phrase, "assist"))

    def test_search_is_owned_by_registry(self):
        result = self.dispatch("where can i watch the matrix")
        self.assertEqual(result.handler, "media_search")
        self.assertIs(result.result.outcome, Outcome.SEARCH_RESULT)
        self.search.assert_called_once_with("where can i watch the matrix")

    def test_search_errors_do_not_fall_through(self):
        self.search.return_value = ("No agent configured.", "not_configured")
        result = self.dispatch("find movie dune")
        self.assertEqual(result.handler, "media_search")
        self.assertIs(result.result.outcome, Outcome.NOT_CONFIGURED)

    def test_music_has_priority_over_media_search(self):
        self.deps.parse_music.return_value = ("music",)
        result = self.dispatch("where can i watch dune")
        self.assertEqual(result.handler, "music_play")
        self.search.assert_not_called()

    def test_unmatched_does_not_call_search(self):
        self.assertIsNone(self.dispatch("turn on kitchen lights"))
        self.search.assert_not_called()

    def test_optional_dependency_keeps_legacy_registry(self):
        original = dependencies()
        self.assertIsNone(commands.registry(original).dispatch(commands.RequestContext("find movie dune", "assist")))
