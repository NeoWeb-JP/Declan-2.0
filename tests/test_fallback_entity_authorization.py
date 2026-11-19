"""Guarded fallback entity authorization regression tests."""
import unittest
from declan.ai.fallback_entity_authorization import exposed_entities


class FallbackEntityAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.token = "a" * 32
        self.body = {"ai_exposed_entities": ["light.kitchen"]}

    def test_valid_token_exposes_entities(self):
        self.assertEqual(exposed_entities(self.body, "Bearer " + self.token, self.token),
                         ["light.kitchen"])

    def test_invalid_token_does_not_expose(self):
        self.assertEqual(exposed_entities(self.body, "Bearer " + "b" * 32, self.token), ())

    def test_short_configured_token_denied(self):
        self.assertEqual(exposed_entities(self.body, "Bearer short", "short"), ())

    def test_empty_configured_token_denied(self):
        self.assertEqual(exposed_entities(self.body, "Bearer ", ""), ())

    def test_missing_authorization_denied(self):
        self.assertEqual(exposed_entities(self.body, "", self.token), ())

    def test_wrong_scheme_denied(self):
        self.assertEqual(exposed_entities(self.body, "Basic " + self.token, self.token), ())

    def test_lowercase_bearer_denied(self):
        self.assertEqual(exposed_entities(self.body, "bearer " + self.token, self.token), ())

    def test_whitespace_suffix_denied(self):
        self.assertEqual(exposed_entities(self.body, "Bearer " + self.token + " ", self.token), ())

    def test_missing_entities_default_empty(self):
        self.assertEqual(exposed_entities({}, "Bearer " + self.token, self.token), ())

    def test_empty_entities_preserved(self):
        self.assertEqual(exposed_entities({"ai_exposed_entities": []}, "Bearer " + self.token, self.token), [])

    def test_entities_passed_without_copy(self):
        self.assertIs(exposed_entities(self.body, "Bearer " + self.token, self.token),
                      self.body["ai_exposed_entities"])
