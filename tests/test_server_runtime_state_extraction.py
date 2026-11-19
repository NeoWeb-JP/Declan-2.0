"""Runtime state extraction regression checks."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import server
import server_runtime_state


class RuntimeStateTests(unittest.TestCase):
    def test_singletons_constructed_once_in_order(self):
        log = Mock()
        logging = SimpleNamespace(getLogger=Mock(return_value=log), INFO=20)
        store = object()
        calls = []
        def factory(name):
            return lambda: calls.append(name) or name
        result = server_runtime_state.create_runtime(
            logging_module=logging,
            session_module=SimpleNamespace(DEFAULT_SESSION_STORE=store),
            arbiter_factory=factory("arbiter"),
            confirmation_factory=factory("confirmation"),
            gates_factory=factory("gates"),
            cooldown_factory=factory("cooldown"),
            registry_factory=factory("registry"),
        )
        self.assertIs(result[0], log)
        self.assertIs(result[1], store)
        self.assertEqual(calls, ["arbiter", "confirmation", "gates", "cooldown", "registry"])
        logging.getLogger.assert_called_once_with("declan.server")
        log.setLevel.assert_called_once_with(20)

    def test_runtime_settings_preserve_vocabulary_objects(self):
        vocabulary = SimpleNamespace(**{name: object() for name in (
            "SEXY_TIME_COMMANDS", "DINNER_PHRASES", "GUEST_MODE_ENTITY",
            "GUEST_REGISTER_ENTITY", "VISITORS_PRESENT_ENTITY", "GUEST_COMMANDS",
            "UNMATCHED_REPLY", "NAME_PATTERN", "CHAT_COMMANDS",
            "GOOD_MORNING_SCRIPT", "GOOD_MORNING_PHRASES",
            "GOOD_NIGHT_SCRIPT", "GOOD_NIGHT_PHRASES"
        )})
        updates = Mock()
        updates.configured_release_version.return_value = "1.0"
        result = server_runtime_state.runtime_settings(updates_module=updates, vocabulary=vocabulary)
        self.assertEqual(result[:3], (300, 52737, "1.0"))
        self.assertIs(result[3], vocabulary.SEXY_TIME_COMMANDS)
        self.assertIs(result[-1], vocabulary.GOOD_NIGHT_PHRASES)
        updates.configured_release_version.assert_called_once_with()

    def test_server_preserves_public_runtime_references(self):
        self.assertIs(server.SESSION_STORE, server.session_store.DEFAULT_SESSION_STORE)
        self.assertIs(server.ROUTINE_EXECUTION_GATES.__class__, server.routine_execution_gates.RoutineExecutionGates)
        self.assertEqual(server.ASSIST_PORT, 52737)


if __name__ == "__main__":
    unittest.main()
