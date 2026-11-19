import unittest
from declan.ai.ai_pricing import charge, model_profile, rate_pair, require_available, RetiredModelError
from datetime import datetime, timezone, timedelta


class PricingTests(unittest.TestCase):
    def profile(self):
        return {**model_profile('gpt-6-luna'), 'model': 'custom-model',
                'input_usd_per_million': '0.000001', 'output_usd_per_million': '3.125001'}

    def test_custom_prices_use_exact_integer_micro_usd_and_round_up(self):
        profile = self.profile()
        self.assertEqual(rate_pair('custom-model', profile), (1, 3125001))
        self.assertEqual(charge('custom-model', {'input_tokens': 1, 'output_tokens': 1}, profile=profile), 4)

    def test_invalid_prices_cannot_become_zero_or_nonfinite_costs(self):
        invalid: object
        for invalid in (0, True, None, [], '0', '-1', 'NaN', 'Infinity', '1e-3', '0.0000001', '1000.000001'):
            with self.subTest(price=invalid), self.assertRaises(ValueError):
                model_profile('custom-model', {**self.profile(), 'input_usd_per_million': invalid})

    def test_profiles_are_bound_to_model_and_shape(self):
        for profile in ({**self.profile(), 'model': 'another-model'},
                        {**self.profile(), 'status': 'unknown'},
                        {**self.profile(), 'retire_on': '2026-02-30'},
                        {**self.profile(), 'reasoning_effort': []},
                        {**self.profile(), 'extra': True}):
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                model_profile('custom-model', profile)

    def test_retirement_blocks_new_requests_but_not_accounting_for_returned_usage(self):
        today = datetime.now(timezone.utc).date()
        for lifecycle in ({'status': 'retired'}, {'retire_on': today.isoformat()},
                          {'retire_on': (today - timedelta(days=1)).isoformat()}):
            profile = model_profile('custom-model', {**self.profile(), **lifecycle})
            with self.assertRaises(RetiredModelError):
                require_available(profile)
            self.assertGreater(charge('custom-model', {'input_tokens': 1, 'output_tokens': 1}, profile=profile), 0)
        require_available({**self.profile(), 'status': 'deprecated'})
        require_available({**self.profile(), 'retire_on': (today + timedelta(days=1)).isoformat()})

    def test_actual_usage_micro_usd(self):
        self.assertEqual(charge("gpt-5-mini", {"input_tokens": 1000, "output_tokens": 500}), 1250)

    def test_missing_usage_fails_closed(self):
        for usage in (None, {}, {"input_tokens": -1, "output_tokens": 10}):
            with self.assertRaises(ValueError):
                charge("gpt-5-mini", usage)

    def test_unknown_model_fails_closed(self):
        with self.assertRaises(ValueError):
            charge("custom-model", {"input_tokens": 1, "output_tokens": 1})


if __name__ == "__main__":
    unittest.main()
