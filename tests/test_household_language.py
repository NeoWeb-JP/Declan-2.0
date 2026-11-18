"""Household display-name privacy, settings validation and speech regressions."""

import unittest
from unittest.mock import patch

import configuration
import household_language
import personality
import personality_policy


class HouseholdNameTests(unittest.TestCase):
    def test_no_private_names_in_checked_in_personality_templates(self):
        for module in (personality, personality_policy):
            for source in (personality.LINES.values() if module is personality
                           else (personality_policy._DINNER_HOME,
                                 personality_policy._MORNING_HOME,
                                 personality_policy._NIGHT_HOME)):
                self.assertNotIn("Jaco", str(source))
                self.assertNotIn("Edd", str(source))
                self.assertNotIn("Finn", str(source))
                self.assertNotIn("Tux", str(source))

    def test_default_names_remain_generic(self):
        with patch.object(household_language.configuration, "get", return_value=""):
            line = household_language.render(
                "{resident_one} and {resident_two} have fed {pet_dog} and {pet_cat}.")
        self.assertEqual(line, "the cook and your partner have fed the dog and the cat.")

    def test_custom_names_are_substituted_at_response_time(self):
        names = {
            "DECLAN_RESIDENT_ONE_NAME": "Alex",
            "DECLAN_RESIDENT_TWO_NAME": "Sam",
            "DECLAN_DOG_NAME": "Buddy",
            "DECLAN_CAT_NAME": "Mittens",
        }
        with patch.object(household_language.configuration, "get",
                          side_effect=lambda key, default: names[key]):
            result = household_language.render(
                "{resident_one} and {resident_two} made dinner for {pet_dog} and {pet_cat}.")
            self.assertEqual(result, "Alex and Sam made dinner for Buddy and Mittens.")
            names["DECLAN_DOG_NAME"] = "Scout"
            self.assertIn("Scout", household_language.render("Hello {pet_dog}."))

    def test_names_must_be_safe_single_line(self):
        for name in ("<script>", "alert()\n", "http://server", "x" * 90, "🚩"):
            with self.subTest(name=name), patch.object(
                household_language.configuration, "get", return_value=name
            ):
                self.assertEqual(household_language.render("Hello {pet_dog}."),
                                 "Hello the dog.")

    def test_settings_import_validates_safe_display_names(self):
        for key in ("DECLAN_RESIDENT_ONE_NAME", "DECLAN_RESIDENT_TWO_NAME",
                    "DECLAN_DOG_NAME", "DECLAN_CAT_NAME"):
            good = {"format": "declan-settings", "schema_version": 1,
                    "settings": {key: "Anne-Marie"}}
            self.assertEqual(configuration.validate(good), good)
            for invalid in ("<script>", "A\nB", "A" * 70):
                with self.subTest(key=key, value=invalid), self.assertRaises(ValueError):
                    configuration.validate({**good, "settings": {key: invalid}})

    def test_original_response_variants_remain_selected(self):
        with patch.object(household_language.configuration, "get", return_value=""):
            samples = [personality_policy.morning_request_reply(visitor_present=False)
                       for _ in range(5)]
        self.assertEqual(len(samples), len(set(samples)))
        self.assertTrue(all("Good morning." in x for x in samples))


if __name__ == "__main__":
    unittest.main()
