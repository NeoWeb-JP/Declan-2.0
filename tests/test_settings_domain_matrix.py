"""Exercise every supported settings import entity domain."""
import unittest

from declan.core import configuration


class SettingsDomainMatrixTests(unittest.TestCase):
    @staticmethod
    def document(key, value):
        return {"format": "declan-settings", "schema_version": 1,
                "settings": {key: value}}

    def test_every_allowlisted_field_accepts_its_domain(self):
        for key, domain in configuration.FIELDS.items():
            value = ("default-pipeline" if domain == "pipeline" else
                     "Test Resident" if domain == "display_name" else f"{domain}.declan_test")
            with self.subTest(key=key, domain=domain):
                self.assertEqual(
                    configuration.validate(self.document(key, value))["settings"][key],
                    value)

    def test_every_allowlisted_field_accepts_empty_fallback(self):
        for key in configuration.FIELDS:
            with self.subTest(key=key):
                self.assertEqual(
                    configuration.validate(self.document(key, ""))["settings"][key], "")

    def test_every_entity_field_rejects_wrong_domain(self):
        for key, domain in configuration.FIELDS.items():
            if domain == "pipeline":
                continue
            wrong = "remote" if domain != "remote" else "script"
            with self.subTest(key=key, domain=domain), self.assertRaises(ValueError):
                configuration.validate(self.document(key, f"{wrong}.declan_test"))

    def test_pipeline_rejects_entity_identifier_and_whitespace(self):
        for value in ("script.test", "pipeline with spaces", "pipeline/one",
                      "pipeline." + "a" * 65):
            with self.subTest(value=value), self.assertRaises(ValueError):
                configuration.validate(
                    self.document("DECLAN_WEB_ASSIST_PIPELINE", value))

    def test_entity_ids_reject_invalid_characters(self):
        for value in ("script.BadCase", "script.bad-name", "script.bad name",
                      "script.name/extra", "script."):
            with self.subTest(value=value), self.assertRaises(ValueError):
                configuration.validate(self.document("DECLAN_MOVIE_SCRIPT", value))


if __name__ == "__main__":
    unittest.main()
