"""Verify imported routine and remote settings cannot target arbitrary HA entities."""
import unittest

from declan.core import configuration


class RoutineSettingsValidationTests(unittest.TestCase):
    @staticmethod
    def document(key, value):
        return {"format": "declan-settings", "schema_version": 1,
                "settings": {key: value}}

    def test_valid_routine_and_remote_entities_are_accepted(self):
        examples = {
            "DECLAN_GOOD_MORNING_SCRIPT": "script.good_morning",
            "DECLAN_GOOD_NIGHT_SCRIPT": "script.good_night",
            "DECLAN_MOVIE_SCRIPT": "script.movie_time",
            "DECLAN_BEDROOM_MOVIE_SCRIPT": "script.bedroom_movie",
            "DECLAN_MOVIE_REMOTE": "remote.projector",
            "DECLAN_BEDROOM_MOVIE_REMOTE": "remote.bedroom",
        }
        for key, value in examples.items():
            for candidate in ("", value):
                with self.subTest(key=key, value=candidate):
                    self.assertEqual(configuration.validate(self.document(key, candidate))[
                        "settings"][key], candidate)

    def test_wrong_domains_and_unsafe_entity_ids_are_rejected(self):
        keys = ("DECLAN_GOOD_MORNING_SCRIPT", "DECLAN_GOOD_NIGHT_SCRIPT",
                "DECLAN_MOVIE_SCRIPT", "DECLAN_BEDROOM_MOVIE_SCRIPT",
                "DECLAN_MOVIE_REMOTE", "DECLAN_BEDROOM_MOVIE_REMOTE")
        for key in keys:
            domain = "remote" if key.endswith("_REMOTE") else "script"
            wrong = "script" if domain == "remote" else "remote"
            for value in (f"{wrong}.example", f"{domain}.", f"{domain}.Upper",
                          f"{domain}.example/other", f"{domain}.example?x=1",
                          f"{domain}.example#fragment", f" {domain}.example ", None, 123):
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    configuration.validate(self.document(key, value))


if __name__ == "__main__":
    unittest.main()
