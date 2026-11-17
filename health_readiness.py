"""Database readiness check for the lightweight HTTP health endpoint."""
import sqlite3

import history
from home_assistant_results import HomeAssistantStatus, HomeAssistantStatusResult


def database_ready():
    """Return False if the configured conversation database cannot be queried."""
    try:
        with history.database() as connection:
            connection.execute("SELECT 1 FROM turns LIMIT 1").fetchone()
        return True
    except (sqlite3.Error, OSError):
        return False


def home_assistant_ready(status: HomeAssistantStatusResult) -> bool:
    """Only a live authenticated HA connection proves dependency readiness."""
    if not isinstance(status, HomeAssistantStatusResult):
        raise TypeError("Expected typed Home Assistant status result.")
    return status.status is HomeAssistantStatus.CONNECTED
