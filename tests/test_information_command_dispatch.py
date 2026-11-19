"""Information command dispatch wiring regression tests."""
import unittest
from unittest.mock import Mock
from declan.turn.information_command_dispatch import dispatch_information


class InformationCommandDispatchTests(unittest.TestCase):
    def setUp(self):
        self.registry = Mock()
        self.registry.dispatch.return_value = "information result"
        self.factory = Mock(return_value=self.registry)
        self.context = Mock(return_value="context")
        self.matches = Mock()
        self.follow_up = Mock()
        self.handle = Mock()
        self.question_context = Mock()
        self.opener = Mock()
        self.last_information = Mock()
        self.decorate = Mock()
        self.guest_mode = Mock()

    def dispatch(self, phrase="what is the weather", source="assist"):
        return dispatch_information(phrase, source=source,
            registry_factory=self.factory, context_factory=self.context,
            matches=self.matches, follow_up=self.follow_up, handle=self.handle,
            question_context=self.question_context, opener=self.opener,
            last_information=self.last_information, decorate=self.decorate,
            guest_mode=self.guest_mode)

    def test_result_returned(self):
        self.assertEqual(self.dispatch(), "information result")

    def test_registry_dependencies(self):
        self.dispatch()
        self.factory.assert_called_once_with(matches=self.matches, follow_up=self.follow_up,
            handle=self.handle, question_context=self.question_context, opener=self.opener,
            last_information=self.last_information, decorate=self.decorate,
            guest_mode=self.guest_mode)

    def test_request_context(self):
        self.dispatch()
        self.context.assert_called_once_with(phrase="what is the weather", source="assist")

    def test_registry_receives_context(self):
        self.dispatch()
        self.registry.dispatch.assert_called_once_with("context")

    def test_no_match_preserved(self):
        self.registry.dispatch.return_value = None
        self.assertIsNone(self.dispatch())

    def test_browser_source_preserved(self):
        self.dispatch(source="browser")
        self.assertEqual(self.context.call_args.kwargs["source"], "browser")

    def test_follow_up_phrase_preserved(self):
        self.dispatch(phrase="and tomorrow?")
        self.assertEqual(self.context.call_args.kwargs["phrase"], "and tomorrow?")

    def test_registry_constructed_once(self):
        self.dispatch()
        self.factory.assert_called_once()

    def test_context_constructed_once(self):
        self.dispatch()
        self.context.assert_called_once()
