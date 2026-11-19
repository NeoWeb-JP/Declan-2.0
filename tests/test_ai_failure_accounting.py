"""Only proven nonbillable failures or known usage release reservations."""
from contextlib import contextmanager
import io
import json
import sqlite3
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import ai_fallback_dispatch
import ai_settings
import ha_inventory
from ai_budget import BudgetExhausted, monthly_reserved
from ai_pricing import charge
from guarded_fallback import run_guarded_result
from model_response_results import NonBillablePlanningError
from openai_planner import request_plan


class FailureAccountingTests(unittest.TestCase):
    def setUp(self):
        self.database = sqlite3.connect(':memory:')
        self.addCleanup(self.database.close)
        self.inventory = [{'entity_id': 'light.kitchen', 'state': 'off', 'attributes': {}}]
        self.dispatcher = Mock()

    def run_plan(self, planner, **kwargs):
        return run_guarded_result('lights on', self.inventory, planner=planner,
                                  dispatcher=self.dispatcher, budget_db=self.database,
                                  monthly_limit_micro_usd=5_000_000,
                                  request_ceiling_micro_usd=50_000, **kwargs)

    def test_one_hundred_unsent_failures_do_not_exhaust_default_budget(self):
        opener = Mock()
        for _ in range(100):
            with self.assertRaises(NonBillablePlanningError):
                self.run_plan(lambda text, exposed: request_plan(
                    text, exposed, model='', api_key='fixture', opener=opener))
        self.assertEqual(monthly_reserved(self.database), 0)
        self.assertEqual(self.database.execute('SELECT count(*) FROM ai_reservation').fetchone()[0], 0)
        opener.open.assert_not_called()
        self.dispatcher.assert_not_called()
        self.run_plan(lambda *_: (), charge_micro_usd=lambda: 10)
        self.assertEqual(monthly_reserved(self.database), 10)

    def test_provider_rejection_releases_reservation(self):
        for status in (400, 401, 403, 404, 405, 413, 415, 422, 429):
            opener = Mock()
            opener.open.side_effect = HTTPError('https://api.openai.com', status, 'rejected', {}, io.BytesIO())
            with self.subTest(status=status), self.assertRaises(NonBillablePlanningError):
                self.run_plan(lambda text, exposed: request_plan(
                    text, exposed, model='gpt-5-mini', api_key='fixture', opener=opener))
            self.assertEqual(monthly_reserved(self.database), 0)
        self.dispatcher.assert_not_called()

    def test_server_errors_without_usage_retain_uncertain_reservation(self):
        for status in (408, 500, 502, 503, 504):
            opener = Mock()
            opener.open.side_effect = HTTPError('https://api.openai.com', status, 'unknown outcome', {}, io.BytesIO())
            with self.subTest(status=status), self.assertRaises(ValueError):
                self.run_plan(lambda text, exposed: request_plan(
                    text, exposed, model='gpt-5-mini', api_key='fixture', opener=opener))
        self.assertEqual(monthly_reserved(self.database), 250_000)
        self.dispatcher.assert_not_called()

    def test_unknown_timeout_or_unclassified_planner_error_retains_ceiling(self):
        for error in (TimeoutError(), URLError('unknown outcome'), ValueError('unclassified')):
            with self.subTest(error=type(error)), self.assertRaises(ValueError if isinstance(error, ValueError) else type(error)):
                self.run_plan(Mock(side_effect=error))
        self.assertEqual(monthly_reserved(self.database), 150_000)
        self.dispatcher.assert_not_called()

    def test_incomplete_response_with_known_usage_settles_actual_cost(self):
        usage = {}
        opener = Mock()
        opener.open.return_value = io.BytesIO(json.dumps({
            'status': 'incomplete', 'usage': {'input_tokens': 10, 'output_tokens': 2}, 'output': []}).encode())
        with self.assertRaisesRegex(ValueError, 'Invalid model plan'):
            self.run_plan(lambda text, exposed: request_plan(
                text, exposed, model='gpt-5-mini', api_key='fixture', opener=opener,
                usage_sink=lambda value: usage.update(value)),
                charge_micro_usd=lambda: charge('gpt-5-mini', usage))
        self.assertEqual(monthly_reserved(self.database), 7)
        self.dispatcher.assert_not_called()

    def test_invalid_or_missing_usage_does_not_refund_unknown_request(self):
        with self.assertLogs('guarded_fallback', level='WARNING'):
            with self.assertRaisesRegex(ValueError, 'original failure'):
                self.run_plan(Mock(side_effect=ValueError('original failure')),
                              charge_micro_usd=Mock(side_effect=ValueError('private provider data')))
        self.assertEqual(monthly_reserved(self.database), 50_000)

    def test_budget_exhaustion_is_explicit_in_spoken_result(self):
        @contextmanager
        def database():
            yield self.database

        result = ai_fallback_dispatch.guarded_openai_fallback_result(
            'turn on kitchen', source='assist', exposed_entities=['light.kitchen'],
            settings_reader=lambda: {**ai_settings.DEFAULTS, 'enabled': True}, intent_gate=lambda _: True,
            connect=lambda: object(), inventory_reader=lambda _: (self.inventory, None),
            inventory_module=ha_inventory, context_selector=lambda rows, *args, **kwargs: rows,
            planner_module=SimpleNamespace(MAX_CONTEXT=100), settings_module=ai_settings,
            history_module=SimpleNamespace(database=database),
            fallback_runner=Mock(side_effect=BudgetExhausted(20_000)),
            dispatcher=self.dispatcher, pricing=charge, bounded_plan=Mock(),
            evidence_factory=Mock(), response_factory=lambda result, *args: result)
        self.assertIn('budget exhausted', result.reply)
        self.assertIn('$0.02 remains', result.reply)
        self.dispatcher.assert_not_called()
