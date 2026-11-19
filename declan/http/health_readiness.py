"""Database readiness check for the lightweight HTTP health endpoint."""
import sqlite3
from dataclasses import dataclass

from declan.core import history
from declan.ha.home_assistant_results import HomeAssistantStatus, HomeAssistantStatusResult


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


def database_health_response() -> tuple[int, dict[str, str]]:
    """Preserve the lightweight database-only health response contract."""
    ready = database_ready()
    return (200 if ready else 503, {"status": "ok" if ready else "unavailable"})


@dataclass(frozen=True)
class DependencyHealth:
    database: bool
    home_assistant: HomeAssistantStatusResult

    @property
    def ready(self) -> bool:
        return self.database and home_assistant_ready(self.home_assistant)

    def response(self) -> tuple[int, dict[str, str]]:
        return (200 if self.ready else 503, {
            "status": "ok" if self.ready else "unavailable",
            "database": "ok" if self.database else "unavailable",
            "home_assistant": self.home_assistant.status.value,
        })
