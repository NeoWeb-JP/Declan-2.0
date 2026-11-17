"""Regression coverage for exported settings schema and import boundaries."""
import unittest

import configuration


class SettingsDocumentValidationTests(unittest.TestCase):
    @staticmethod
    def document(**changes):
        result = {"format": "declan-settings", "schema_version": 1, "settings": {}}
        result.update(changes)
        return result

    def test_valid_empty_settings_document(self):
        self.assertEqual(configuration.validate(self.document())["settings"], {})

    def test_rejects_invalid_document_shape_and_schema(self):
        invalid = (
            None, [], "settings", {},
            self.document(format="other"),
            self.document(schema_version=0),
            self.document(schema_version=True),
            self.document(schema_version="1"),
            self.document(settings=[]),
            self.document(extra="unexpected"),
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                configuration.validate(value)

    def test_rejects_secrets_and_unknown_setting_names(self):
        for key in ("DECLAN_HA_TOKEN", "OPENAI_API_KEY", "DECLAN_UNRECOGNISED"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                configuration.validate(self.document(settings={key: "secret"}))

    def test_rejects_oversized_entity_value(self):
        with self.assertRaises(ValueError):
            configuration.validate(self.document(
                settings={"DECLAN_MOVIE_SCRIPT": "script." + "a" * 130}))


if __name__ == "__main__":
    unittest.main()
