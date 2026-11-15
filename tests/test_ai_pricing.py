import unittest
from ai_pricing import charge


class PricingTests(unittest.TestCase):
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
