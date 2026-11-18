"""Turn persistence dispatch regression tests."""
import unittest
from unittest.mock import Mock
from turn_persistence_orchestration import persist_turn


class TurnPersistenceDispatchTests(unittest.TestCase):
    def setUp(self):
        self.reply = {"session_id": "abc", "reply": "Done"}
        self.session = {"history": []}
        self.sessions = {"abc": self.session}
        self.finalize = Mock(return_value="persisted")
        self.deps = {name: Mock() for name in (
            "similar", "normalize_phrase", "teach_phrase", "record",
            "diagnostic_id", "log_error", "state_module", "training_module",
            "history_module")}
        self.actions = {"light.turn_on"}
        self.action_results = [{"action": "light.turn_on"}]

    def persist(self, **overrides):
        args = dict(sessions=self.sessions, finalize=self.finalize,
            message="turn on light", phrase="turn on light", outcome="confirmed",
            scope="kitchen", status_target="light.kitchen", information_context=None,
            light_result=("Done", "confirmed"), action_results=self.action_results,
            actions=self.actions, unmatched_reply="Unmatched", now=123.0,
            pending_retry=None, effective_message="turn on light",
            source="assist", routine_status=None, phrase_suggestion=None,
            speaker="Jaco", **self.deps)
        args.update(overrides)
        return persist_turn(self.reply, **args)

    def test_finalizer_return_value(self):
        self.assertEqual(self.persist(), "persisted")

    def test_finalizer_called_once(self):
        self.persist()
        self.finalize.assert_called_once()

    def test_session_selected_from_reply(self):
        self.persist()
        self.assertIs(self.finalize.call_args.kwargs["session"], self.session)

    def test_reply_passed_by_reference(self):
        self.persist()
        self.assertIs(self.finalize.call_args.args[0], self.reply)

    def test_action_results_passed_by_reference(self):
        self.persist()
        self.assertIs(self.finalize.call_args.kwargs["action_results"], self.action_results)

    def test_actions_passed_by_reference(self):
        self.persist()
        self.assertIs(self.finalize.call_args.kwargs["actions"], self.actions)

    def test_source_and_speaker_forwarded(self):
        self.persist(source="browser", speaker="Edd")
        self.assertEqual(self.finalize.call_args.kwargs["source"], "browser")
        self.assertEqual(self.finalize.call_args.kwargs["speaker"], "Edd")

    def test_diagnostic_callback_forwarded(self):
        self.persist()
        self.assertIs(self.finalize.call_args.kwargs["diagnostic_id"], self.deps["diagnostic_id"])

    def test_training_modules_forwarded(self):
        self.persist()
        self.assertIs(self.finalize.call_args.kwargs["training_module"], self.deps["training_module"])
        self.assertIs(self.finalize.call_args.kwargs["history_module"], self.deps["history_module"])

    def test_missing_session_raises(self):
        with self.assertRaises(KeyError):
            self.persist(sessions={})

    def test_missing_session_does_not_finalize(self):
        with self.assertRaises(KeyError):
            self.persist(sessions={})
        self.finalize.assert_not_called()
