"""Device command registry wiring regression tests."""
import unittest
from unittest.mock import Mock
from declan.ha.device_command_dispatch import dispatch_device


class DeviceCommandDispatchTests(unittest.TestCase):
    def setUp(self):
        self.registry = Mock()
        self.registry.dispatch.return_value = "device result"
        self.registry_factory = Mock(return_value=self.registry)
        self.dependencies_factory = Mock(return_value="dependencies")
        self.context_factory = Mock(return_value="context")
        self.deps = {name: Mock() for name in (
            "parse_status", "describe_status", "connection", "inventory", "decorate",
            "guest_mode_entity", "parse_feedback", "feedback", "parse_control",
            "control", "parse_music", "play", "music_inventory", "areas", "search_media",
            "parse_extra", "extra")}

    def dispatch(self, **overrides):
        request = dict(phrase="music please", source="assist", last_device="speaker",
                       origin_device="kitchen", satellite="satellite.kitchen")
        request.update(overrides)
        return dispatch_device(**request, registry_factory=self.registry_factory,
            dependencies_factory=self.dependencies_factory,
            context_factory=self.context_factory, **self.deps)

    def test_result_returned(self):
        self.assertEqual(self.dispatch(), "device result")

    def test_dependencies_forwarded(self):
        self.dispatch()
        self.dependencies_factory.assert_called_once_with(**self.deps)

    def test_registry_receives_dependencies(self):
        self.dispatch()
        self.registry_factory.assert_called_once_with("dependencies")

    def test_context_preserves_origin_and_last_device(self):
        self.dispatch()
        self.context_factory.assert_called_once_with(
            phrase="music please", source="assist", last_device="speaker",
            origin_device="kitchen", satellite="satellite.kitchen")

    def test_dispatch_receives_context(self):
        self.dispatch()
        self.registry.dispatch.assert_called_once_with("context")

    def test_unmatched_result_preserved(self):
        self.registry.dispatch.return_value = None
        self.assertIsNone(self.dispatch())

    def test_browser_source_preserved(self):
        self.dispatch(source="browser")
        self.assertEqual(self.context_factory.call_args.kwargs["source"], "browser")

    def test_missing_device_preserved(self):
        self.dispatch(last_device=None, origin_device=None, satellite=None)
        self.assertIsNone(self.context_factory.call_args.kwargs["last_device"])
        self.assertIsNone(self.context_factory.call_args.kwargs["origin_device"])
        self.assertIsNone(self.context_factory.call_args.kwargs["satellite"])

    def test_registry_constructed_once(self):
        self.dispatch()
        self.registry_factory.assert_called_once()
