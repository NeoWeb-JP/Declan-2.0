"""Stop command dispatch wiring regression tests."""
import unittest
from unittest.mock import Mock
from declan.music.stop_command_dispatch import dispatch_stop


class StopCommandDispatchTests(unittest.TestCase):
    def setUp(self):
        self.registry = Mock()
        self.registry.dispatch.return_value = "stop result"
        self.factory = Mock(return_value=self.registry)
        self.context = Mock(return_value="context")
        self.stop_routines = Mock()
        self.stop_everywhere = Mock()
        self.connection = Mock()

    def dispatch(self, phrase="stop", source="assist", origin="kitchen", satellite="satellite.kitchen"):
        return dispatch_stop(phrase, source=source, origin_device=origin,
            satellite=satellite, registry_factory=self.factory,
            context_factory=self.context, stop_routines=self.stop_routines,
            stop_everywhere=self.stop_everywhere, connection=self.connection)

    def test_result_returned(self):
        self.assertEqual(self.dispatch(), "stop result")

    def test_registry_dependencies(self):
        self.dispatch()
        self.factory.assert_called_once_with(stop_routines=self.stop_routines,
            stop_everywhere=self.stop_everywhere, connection=self.connection)

    def test_request_context(self):
        self.dispatch()
        self.context.assert_called_once_with(phrase="stop", source="assist",
            origin_device="kitchen", satellite="satellite.kitchen")

    def test_registry_receives_context(self):
        self.dispatch()
        self.registry.dispatch.assert_called_once_with("context")

    def test_no_match_preserved(self):
        self.registry.dispatch.return_value = None
        self.assertIsNone(self.dispatch())

    def test_browser_source_preserved(self):
        self.dispatch(source="browser")
        self.assertEqual(self.context.call_args.kwargs["source"], "browser")

    def test_missing_origin_preserved(self):
        self.dispatch(origin=None, satellite=None)
        self.assertIsNone(self.context.call_args.kwargs["origin_device"])
        self.assertIsNone(self.context.call_args.kwargs["satellite"])

    def test_stop_music_phrase_preserved(self):
        self.dispatch(phrase="stop the music")
        self.assertEqual(self.context.call_args.kwargs["phrase"], "stop the music")

    def test_registry_constructed_once(self):
        self.dispatch()
        self.factory.assert_called_once()
