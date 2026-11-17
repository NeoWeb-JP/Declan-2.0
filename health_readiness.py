"""Database readiness check for the lightweight HTTP health endpoint."""
import sqlite3

import history


def database_ready():
    """Return False if the configured conversation database cannot be queried."""
    try:
        with history.database() as connection:
            connection.execute("SELECT 1 FROM turns LIMIT 1").fetchone()
        return True
    except (sqlite3.Error, OSError):
        return False
