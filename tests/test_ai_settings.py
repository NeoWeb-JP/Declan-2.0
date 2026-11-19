import unittest
import sqlite3
from contextlib import contextmanager
from unittest.mock import patch
from declan.ai import ai_settings
from declan.ai import ai_budget
from declan.ai.ai_settings import DEFAULTS, validate
from declan.ai.ai_pricing import model_profile


class AISettingsTests(unittest.TestCase):
    def test_legacy_documents_upgrade_without_changing_model_or_enablement(self):
        old = {key: value for key, value in DEFAULTS.items() if key != 'model_config'}
        for model in ('gpt-5-mini', 'gpt-6-luna'):
            configured = validate({**old, 'enabled': True, 'model': model})
            self.assertTrue(configured['enabled'])
            self.assertEqual(configured['model'], model)
            self.assertEqual(configured['model_config']['model'], model)
        self.assertEqual(validate(old)['model_config']['status'], 'deprecated')

    def test_custom_profile_round_trip_and_retired_settings_remain_readable(self):
        connection = sqlite3.connect(':memory:')
        self.addCleanup(connection.close)
        @contextmanager
        def database():
            with connection:
                yield connection
        profile = {**model_profile('gpt-6-luna'), 'model': 'custom-model'}
        with patch.object(ai_settings, 'database', database):
            saved = ai_settings.save(dict(DEFAULTS, model='custom-model', enabled=True, model_config=profile))
            self.assertEqual(ai_settings.read(), saved)
            # A saved date can become past while the application is running.
            profile['retire_on'] = '2000-01-01'
            import json
            connection.execute('UPDATE ai_settings SET document=?', (
                json.dumps({**saved, 'model_config': profile}),))
            expired = ai_settings.read()
            self.assertTrue(expired['enabled'])
            with self.assertRaises(ValueError):
                ai_settings.save(expired)
            ai_settings.save({**expired, 'enabled': False})
            self.assertFalse(ai_settings.read()['enabled'])

    def test_monthly_usage_before_first_ai_request(self):
        db = sqlite3.connect(":memory:")
        try:
            self.assertEqual(ai_budget.monthly_reserved(db), 0)
            self.assertIsNone(db.execute(
                "SELECT name FROM sqlite_master WHERE name='ai_budget'"
            ).fetchone())
            ai_budget.reserve(db, limit_micro_usd=1000000,
                              max_request_micro_usd=50000)
            self.assertEqual(ai_budget.monthly_reserved(db), 50000)
        finally:
            db.close()

    def test_persist_and_reload(self):
        connection = sqlite3.connect(":memory:")
        @contextmanager
        def database():
            with connection:
                yield connection
        try:
            with patch.object(ai_settings, "database", database):
                self.assertFalse(ai_settings.read()["enabled"])
                settings = dict(DEFAULTS, enabled=True)
                ai_settings.save(settings)
                self.assertTrue(ai_settings.read()["enabled"])
        finally:
            connection.close()

    def test_safe_defaults(self):
        self.assertFalse(validate(dict(DEFAULTS))["enabled"])

    def test_approved_policies_are_fixed(self):
        for key, value in (("confirmation", "all"), ("routines", "all"), ("ambiguous", "guess")):
            with self.subTest(key=key):
                payload = dict(DEFAULTS, **{key: value})
                with self.assertRaises(ValueError):
                    validate(payload)

    def test_budget_must_cover_request(self):
        payload = dict(DEFAULTS, enabled=True, monthly_budget_usd="0.01")
        with self.assertRaises(ValueError):
            validate(payload)

    def test_unknown_domain_rejected(self):
        payload = dict(DEFAULTS, allowed_domains=["lock"])
        with self.assertRaises(ValueError):
            validate(payload)

    def test_action_count_bounded(self):
        with self.assertRaises(ValueError):
            validate(dict(DEFAULTS, max_actions=9))


if __name__ == "__main__":
    unittest.main()
