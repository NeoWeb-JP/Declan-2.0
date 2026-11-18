"""Turn finalization dispatch boundary regressions."""

import unittest
from unittest.mock import Mock

from turn_finalization_dispatch import (
    prepare_context, compose_response, persist_response,
)


class TurnFinalizationDispatchTests(unittest.TestCase):
    def test_context_preparation_preserves_action_evidence(self):
        prepare = Mock(return_value=(["actions"], "suggestion"))
        dependencies = dict(
            action_results=["lights"], light_result="light", outcome="done",
            scope="room", message="lights on", now=42,
            suggestion_factory=Mock(),
        )
        result = prepare_context("previous", prepare=prepare, **dependencies)
        self.assertEqual(result, (["actions"], "suggestion"))
        prepare.assert_called_once_with("previous", **dependencies)

    def test_composition_preserves_response_and_context(self):
        compose = Mock(return_value="typed-response")
        dependencies = dict(
            lighting_context="lighting", routine_voice_result="voice",
            routine_status="completed", outcome="done",
        )
        self.assertEqual(compose_response(
            "hello", "session", "reply", compose_turn=compose, **dependencies,
        ), "typed-response")
        compose.assert_called_once_with(
            "hello", "session", "reply", **dependencies,
        )

    def test_persistence_preserves_result_and_evidence(self):
        persist = Mock(return_value="saved")
        dependencies = dict(
            sessions={}, actions=["light"], pending_retry=None,
            speaker="speaker", diagnostic_id="trace",
        )
        self.assertEqual(persist_response(
            "response", persist=persist, **dependencies,
        ), "saved")
        persist.assert_called_once_with("response", **dependencies)


if __name__ == "__main__":
    unittest.main()
