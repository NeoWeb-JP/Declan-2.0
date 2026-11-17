"""Database health should reflect actual query readiness."""
import sqlite3
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import health_readiness


class DatabaseHealthTests(unittest.TestCase):
    def test_healthy_database(self):
        connection = sqlite3.connect(":memory:")
        connection.execute("CREATE TABLE turns (id INTEGER PRIMARY KEY)")

        @contextmanager
        def database():
            yield connection

        try:
            with patch.object(health_readiness.history, "database", database):
                self.assertTrue(health_readiness.database_ready())
        finally:
            connection.close()

    def test_missing_table_is_unhealthy(self):
        connection = sqlite3.connect(":memory:")

        @contextmanager
        def database():
            yield connection

        try:
            with patch.object(health_readiness.history, "database", database):
                self.assertFalse(health_readiness.database_ready())
        finally:
            connection.close()

    def test_connection_failure_is_unhealthy(self):
        @contextmanager
        def database():
            raise sqlite3.OperationalError("database unavailable")
            yield

        with patch.object(health_readiness.history, "database", database):
            self.assertFalse(health_readiness.database_ready())


if __name__ == "__main__":
    unittest.main()
