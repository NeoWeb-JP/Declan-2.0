import unittest
from ai_settings import DEFAULTS, validate


class AISettingsTests(unittest.TestCase):
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
