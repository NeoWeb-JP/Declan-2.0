"""Verify exported settings validate browser Assist pipeline identifiers."""
import unittest

import configuration


class AssistPipelineSettingsValidationTests(unittest.TestCase):
    @staticmethod
    def document(value):
        return {"format": "declan-settings", "schema_version": 1,
                "settings": {"DECLAN_WEB_ASSIST_PIPELINE": value}}

    def test_valid_pipeline_identifiers_are_accepted(self):
        for value in ("", "default", "Pipeline_123", "pipeline-123", "a" * 64):
            with self.subTest(value=value):
                self.assertEqual(configuration.validate(self.document(value))["settings"][
                    "DECLAN_WEB_ASSIST_PIPELINE"], value)

    def test_invalid_pipeline_identifiers_are_rejected(self):
        for value in ("a" * 65, "pipeline with spaces", "pipeline/other", "../pipeline",
                      "pipeline?secret=x", "pipeline#fragment", "pipeline.name",
                      " pipeline ", "é", 123, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                configuration.validate(self.document(value))

    def test_unknown_settings_cannot_be_imported(self):
        with self.assertRaises(ValueError):
            configuration.validate({"format": "declan-settings", "schema_version": 1,
                                    "settings": {"DECLAN_UNLISTED_SETTING": "value"}})


if __name__ == "__main__":
    unittest.main()
