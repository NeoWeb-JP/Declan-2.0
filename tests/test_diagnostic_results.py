"""Typed diagnostic decisions retain public mappings and bounded plain storage."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch

import diagnostics
from execution_results import ExecutionResult, Outcome


class DiagnosticResultTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(TemporaryDirectory())
        self.enterContext(patch.object(diagnostics, 'DATABASE', Path(folder) / 'diagnostics.db'))

    def test_typed_execution_and_legacy_results_retain_identity_and_outcomes(self):
        values: list[tuple[object, str]] = [(ExecutionResult('Reply', outcome), outcome.value) for outcome in Outcome]
        values.extend([((ExecutionResult('Reply', Outcome.PARTIAL), 'detail'), 'partial'),
                       (('Reply', 'future_status'), 'future_status'), (True, 'confirmed'),
                       (False, 'unverified'), (None, 'completed')])
        with diagnostics.request('/api/chat') as trace:
            for value, expected in values:
                with self.subTest(expected=expected):
                    result = diagnostics.timed('provider')(lambda: value)()
                    self.assertIs(result, value)
                    self.assertEqual(trace['stages'][-1]['outcome'], expected)
                    self.assertIs(type(trace['stages'][-1]['outcome']), str)
                    self.assertNotIn('_result', trace['stages'][-1])
            diagnostics.set_outcome(trace, Outcome.PARTIAL)
            self.assertIs(diagnostics.outcome_result(trace).status, Outcome.PARTIAL)
            self.assertIs(type(trace['outcome']), str)
        saved = diagnostics.recent()[0]
        self.assertEqual(saved['outcome'], 'partial')
        self.assertNotIn('_result', saved)
        self.assertNotIn('Reply', json.dumps(saved))
        self.assertNotIn('detail', json.dumps(saved))

    def test_legacy_mutation_is_reinterpreted_and_unknown_values_preserved(self):
        with diagnostics.request('/api/chat') as trace:
            self.assertIs(diagnostics.outcome_result(trace).status, diagnostics.DiagnosticOutcome.UNKNOWN)
            trace['outcome'] = 'confirmed'
            self.assertIs(diagnostics.outcome_result(trace).status, Outcome.CONFIRMED)
            trace['outcome'] = 'future_status'
            result = diagnostics.outcome_result(trace)
            self.assertIsNone(result.status)
            self.assertEqual(result.wire_value, 'future_status')
            with self.assertRaises(AttributeError):
                setattr(result, 'status', Outcome.CONFIRMED)
        self.assertEqual(diagnostics.recent()[0]['outcome'], 'future_status')

    def test_failure_after_early_save_replaces_success_without_exception_text(self):
        with self.assertRaises(ValueError):
            with diagnostics.request('/api/chat') as trace:
                diagnostics.set_outcome(trace, Outcome.CONFIRMED)
                diagnostics.persist(trace)
                with diagnostics.stage('provider'):
                    raise ValueError('secret transcript and token')
        self.assertIsNone(diagnostics.ACTIVE.get())
        saved = diagnostics.recent()[0]
        self.assertEqual(saved['outcome'], 'failed')
        self.assertEqual(saved['stages'][0]['error'], 'ValueError')
        self.assertNotIn('secret', json.dumps(saved))

    def test_stages_remain_bounded_and_contexts_restore(self):
        with diagnostics.request('/outer') as outer:
            with diagnostics.request('/inner') as inner:
                self.assertEqual(diagnostics.current_id(), inner['id'])
            self.assertEqual(diagnostics.current_id(), outer['id'])
            for _ in range(85):
                with diagnostics.stage('bounded'):
                    pass
            self.assertEqual(len(outer['stages']), 80)
        self.assertIsNone(diagnostics.ACTIVE.get())
