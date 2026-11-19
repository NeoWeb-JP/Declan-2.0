"""Automatic voice retry training persistence regression tests."""
from typing import Any
import sqlite3
import unittest
from unittest.mock import Mock
from declan.turn.retry_training_persistence import save_retry_training


class RetryTrainingPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.teach = Mock()
        self.log = Mock()
        self.similar = Mock(return_value=True)
        self.normalize = lambda text: text.casefold().strip()

    def save(self, *, pending=None, succeeded=True, message="turn the kitchen light off",
             effective="turn off kitchen lights"):
        reply: dict[str, Any]
        reply = {}
        result = save_retry_training(reply,
            pending_retry={"text": "turn kitchen lights off"} if pending is None else pending,
            retry_succeeded=succeeded, message=message, effective_message=effective,
            similar=self.similar, normalize_phrase=self.normalize,
            teach_phrase=self.teach, log_error=self.log)
        return reply, result

    def test_similar_successful_retry_is_learned(self):
        reply, result = self.save()
        self.assertTrue(result)
        self.assertTrue(reply["learned_from_retry"])
        self.teach.assert_called_once_with("turn kitchen lights off",
                                          "turn off kitchen lights", automatic=True)

    def test_unsuccessful_retry_is_not_learned(self):
        reply, result = self.save(succeeded=False)
        self.assertFalse(result)
        self.assertNotIn("learned_from_retry", reply)
        self.teach.assert_not_called()

    def test_unrelated_request_is_not_learned(self):
        self.similar.return_value = False
        _, result = self.save()
        self.assertFalse(result)
        self.teach.assert_not_called()

    def test_same_normalized_phrase_is_not_learned(self):
        _, result = self.save(effective="TURN KITCHEN LIGHTS OFF")
        self.assertFalse(result)
        self.teach.assert_not_called()

    def test_database_failure_does_not_claim_learning(self):
        self.teach.side_effect = sqlite3.OperationalError("database locked")
        reply, result = self.save()
        self.assertFalse(result)
        self.assertNotIn("learned_from_retry", reply)
        self.log.assert_called_once()

    def test_corrupt_pending_retry_does_not_learn_or_call_similarity(self):
        pending: object
        for pending in ([], {}, {"text": None}, {"text": 42},
                        {"text": ""}, {"text": " "}, {"text": "x" * 4097}):
            with self.subTest(pending=repr(type(pending))):
                self.similar.reset_mock()
                self.teach.reset_mock()
                reply, result = self.save(pending=pending)
                self.assertFalse(result)
                self.assertNotIn("learned_from_retry", reply)
                self.similar.assert_not_called()
                self.teach.assert_not_called()

    def test_similarity_or_normalization_errors_do_not_break_turn(self):
        for stage in ("similarity", "normalization"):
            with self.subTest(stage=stage):
                self.setUp()
                if stage == "similarity":
                    self.similar.side_effect = TypeError("invalid similarity input")
                else:
                    self.normalize = Mock(side_effect=ValueError("bad normalization"))
                reply, result = self.save()
                self.assertFalse(result)
                self.assertNotIn("learned_from_retry", reply)
                self.teach.assert_not_called()
                self.log.assert_called_once()

    def test_invalid_corrected_or_effective_phrases_do_not_learn(self):
        kwargs: dict[str, Any]
        value: object
        for value in (None, 42, [], "", "  ", "x" * 4097):
            for field in ("message", "effective"):
                with self.subTest(field=field, value_type=type(value).__name__):
                    self.similar.reset_mock()
                    self.teach.reset_mock()
                    kwargs = {field: value}
                    reply, result = self.save(**kwargs)
                    self.assertFalse(result)
                    self.assertNotIn("learned_from_retry", reply)
                    self.similar.assert_not_called()
                    self.teach.assert_not_called()

    def test_string_subclass_does_not_execute_custom_normalization(self):
        kwargs: dict[str, Any]
        class HostileText(str):
            def strip(self, chars: str | None = None) -> str:
                raise RuntimeError("unexpected string operation")
        for field in ("pending", "message", "effective"):
            with self.subTest(field=field):
                self.similar.reset_mock()
                self.teach.reset_mock()
                value = HostileText("turn kitchen lights off")
                kwargs = {field: {"text": value} if field == "pending" else value}
                reply, result = self.save(**kwargs)
                self.assertFalse(result)
                self.assertNotIn("learned_from_retry", reply)
                self.similar.assert_not_called()
                self.teach.assert_not_called()

    def test_missing_pending_retry_does_not_learn(self):
        reply: dict[str, Any]
        reply = {}
        result = save_retry_training(reply, pending_retry=None, retry_succeeded=True,
            message="hello", effective_message="hello", similar=self.similar,
            normalize_phrase=self.normalize, teach_phrase=self.teach, log_error=self.log)
        self.assertFalse(result)
        self.teach.assert_not_called()
