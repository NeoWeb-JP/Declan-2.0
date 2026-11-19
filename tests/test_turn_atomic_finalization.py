"""Atomic finalization stage regression tests."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from declan.turn import turn_atomic_finalization


class AtomicFinalizationTests(unittest.TestCase):
    def test_context_compose_persist_under_one_lock(self):
        events = []
        class TrackedLock:
            def __enter__(self):
                events.append("lock")
            def __exit__(self, *_):
                events.append("unlock")
        def prepare(*args, **kwargs):
            events.append("context")
            return ["action"], "suggestion"
        def compose(*args, **kwargs):
            events.append("compose")
            return SimpleNamespace(reply="reply")
        def persist(response, **kwargs):
            events.append("persist")
            self.assertEqual(kwargs["actions"], ["action"])
            self.assertEqual(kwargs["phrase_suggestion"], "suggestion")
            return response
        empty = SimpleNamespace()
        history = SimpleNamespace(normalize_phrase=Mock(), teach_phrase=Mock(), record=Mock())
        result = turn_atomic_finalization.finalize(
            "session", [], None, "ok", None, "hello", "hello", "reply",
            None, False, None, "hello", False, False, None, None,
            None, None, None, "assist", {},
            sessions={}, session_lock=TrackedLock(), clock=lambda: 1.0,
            turn_context_preparation=SimpleNamespace(prepare_turn_context=prepare),
            turn_finalization=SimpleNamespace(lighting_phrase_suggestion=Mock(), apply_outcome_metadata=Mock()),
            turn_response_composition=SimpleNamespace(compose_turn_result=compose),
            turn_response_orchestration=SimpleNamespace(compose=Mock()),
            personality_policy=empty, personality_lines={}, music=SimpleNamespace(parse=Mock(), parse_control=Mock()),
            routine_responses=SimpleNamespace(render=Mock()),
            lighting_intents=SimpleNamespace(response_category=Mock()),
            parse_light_command=Mock(), command_responses=SimpleNamespace(failure=Mock()),
            response_composition=empty,
            turn_persistence_orchestration=SimpleNamespace(persist_turn_result=persist, finalize_turn=Mock()),
            unmatched_reply="unmatched", retry_learning=SimpleNamespace(similar=Mock()),
            history=history, diagnostics=SimpleNamespace(current_id=Mock()),
            session_turn_state=empty, retry_training_persistence=empty,
            conversation_persistence=empty, log_error=Mock(), converse=Mock(),
        )
        self.assertEqual(events, ["lock", "context", "compose", "persist", "unlock"])
        self.assertEqual(result.reply, "reply")


if __name__ == "__main__":
    unittest.main()
