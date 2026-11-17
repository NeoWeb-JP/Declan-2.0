"""Check runtime configuration precedence and environment defaults."""
import os
import unittest
from unittest.mock import patch

import configuration


class ConfigurationEnvironmentFallbackTests(unittest.TestCase):
    def test_non_field_uses_environment_without_database(self):
        with patch.dict(os.environ, {"DECLAN_EXAMPLE_SETTING": "from-env"}):
            with patch.object(configuration.history, "database", side_effect=AssertionError("database accessed")):
                self.assertEqual(configuration.get("DECLAN_EXAMPLE_SETTING"), "from-env")
                self.assertEqual(configuration.get("DECLAN_EXAMPLE_SETTING", "fallback"), "from-env")

    def test_non_field_uses_supplied_default_when_unset(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(configuration.history, "database", side_effect=AssertionError("database accessed")):
                self.assertEqual(configuration.get("DECLAN_EXAMPLE_SETTING"), "")
                self.assertEqual(configuration.get("DECLAN_EXAMPLE_SETTING", "fallback"), "fallback")

    def test_field_falls_back_to_environment_without_stored_value(self):
        class FakeDatabase:
            def execute(self, statement, params=None):
                if statement.startswith("SELECT value"):
                    return self
                return self

            def fetchone(self):
                return None

        from contextlib import contextmanager

        @contextmanager
        def database():
            yield FakeDatabase()

        with patch.dict(os.environ, {"DECLAN_GOOD_MORNING_SCRIPT": "script.morning"}):
            with patch.object(configuration.history, "database", database):
                self.assertEqual(configuration.get("DECLAN_GOOD_MORNING_SCRIPT"), "script.morning")


    def test_saved_nonempty_setting_overrides_environment(self):
        from contextlib import contextmanager

        class FakeDatabase:
            def execute(self, statement, params=None):
                return self

            def fetchone(self):
                return ("script.saved_morning",)

        @contextmanager
        def database():
            yield FakeDatabase()

        with patch.dict(os.environ, {"DECLAN_GOOD_MORNING_SCRIPT": "script.environment"}):
            with patch.object(configuration.history, "database", database):
                self.assertEqual(configuration.get("DECLAN_GOOD_MORNING_SCRIPT"), "script.saved_morning")

    def test_saved_empty_setting_uses_environment_or_supplied_default(self):
        from contextlib import contextmanager

        class FakeDatabase:
            def execute(self, statement, params=None):
                return self

            def fetchone(self):
                return ("",)

        @contextmanager
        def database():
            yield FakeDatabase()

        with patch.object(configuration.history, "database", database):
            with patch.dict(os.environ, {"DECLAN_GOOD_MORNING_SCRIPT": "script.environment"}):
                self.assertEqual(configuration.get("DECLAN_GOOD_MORNING_SCRIPT"), "script.environment")
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(configuration.get("DECLAN_GOOD_MORNING_SCRIPT", "script.default"), "script.default")

if __name__ == "__main__":
    unittest.main()
