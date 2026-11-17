"""Learned intent resolution and fallback regression tests."""
import sqlite3
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from learned_intent_resolution import resolve


class LearnedIntentResolutionTests(unittest.TestCase):
    def setUp(self):
        self.preprocess = Mock(side_effect=lambda message: SimpleNamespace(commands=[message]))
        self.normalize = Mock(side_effect=lambda message: message.lower().strip())
        self.learned = Mock(return_value=None)
        self.log_error = Mock()

    def run_resolution(self, message):
        return resolve(message, preprocess=self.preprocess, normalize=self.normalize,
                       learned_intent=self.learned, log_error=self.log_error)

    def test_untrained_message_unchanged(self):
        self.assertEqual(self.run_resolution("Hello"), ("Hello", "hello"))

    def test_self_correction_precedes_lookup(self):
        self.preprocess.return_value = SimpleNamespace(commands=["turn on kitchen light"])
        self.preprocess.side_effect = None
        self.run_resolution("no, turn on kitchen light")
        self.learned.assert_called_once_with("turn on kitchen light")

    def test_preprocess_value_error_falls_back_to_original(self):
        self.preprocess.side_effect = ValueError("ambiguous")
        self.assertEqual(self.run_resolution("Original"), ("Original", "original"))

    def test_learned_alias_is_applied_once(self):
        self.learned.return_value = "Turn on lights"
        self.assertEqual(self.run_resolution("lights please"), ("Turn on lights", "turn on lights"))
        self.learned.assert_called_once()

    def test_long_phrase_skips_lookup(self):
        self.run_resolution("a" * 121)
        self.learned.assert_not_called()

    def test_invalid_alias_is_ignored(self):
        self.learned.return_value = 42
        self.assertEqual(self.run_resolution("hello"), ("hello", "hello"))

    def test_long_alias_is_ignored(self):
        self.learned.return_value = "x" * 121
        self.assertEqual(self.run_resolution("hello"), ("hello", "hello"))

    def test_sqlite_error_is_logged_and_nonfatal(self):
        self.learned.side_effect = sqlite3.Error("db unavailable")
        self.assertEqual(self.run_resolution("hello"), ("hello", "hello"))
        self.log_error.assert_called_once()

    def test_os_error_is_logged_and_nonfatal(self):
        self.learned.side_effect = OSError("disk error")
        self.assertEqual(self.run_resolution("hello"), ("hello", "hello"))
        self.log_error.assert_called_once()

    def test_max_length_alias_accepted(self):
        self.learned.return_value = "a" * 120
        self.assertEqual(self.run_resolution("hello")[0], "a" * 120)
