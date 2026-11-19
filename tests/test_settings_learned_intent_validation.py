"""Verify learned intention import boundaries in settings documents."""
import unittest

from declan.core import configuration


class LearnedIntentImportValidationTests(unittest.TestCase):
    @staticmethod
    def document(aliases):
        return {"format": "declan-settings", "schema_version": 1,
                "settings": {}, "learned_intents": aliases}

    def test_valid_normalized_alias_is_accepted(self):
        aliases = {"turn on the office light": "turn on the study light"}
        self.assertEqual(configuration.validate(self.document(aliases))["learned_intents"], aliases)

    def test_empty_aliases_are_accepted(self):
        self.assertEqual(configuration.validate(self.document({}))["learned_intents"], {})

    def test_rejects_invalid_alias_containers(self):
        for aliases in (None, [], "text", list(range(3)),
                        {f"alias {i}": f"target {i}" for i in range(501)}):
            with self.subTest(kind=type(aliases).__name__), self.assertRaises(ValueError):
                configuration.validate(self.document(aliases))

    def test_rejects_invalid_alias_and_target_values(self):
        cases = (
            {"": "valid target"},
            {"valid alias": ""},
            {"same phrase": "same phrase"},
            {"Mixed CASE": "valid target"},
            {"valid alias": "Mixed CASE"},
            {"valid alias": "target\ncommand"},
            {"bad\talias": "valid target"},
            {"a" * 121: "valid target"},
            {"valid alias": "a" * 121},
            {123: "valid target"},
            {"valid alias": None},
        )
        for aliases in cases:
            with self.subTest(aliases=repr(aliases)), self.assertRaises(ValueError):
                configuration.validate(self.document(aliases))


if __name__ == "__main__":
    unittest.main()
