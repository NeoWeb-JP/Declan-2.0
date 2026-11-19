"""Compatibility name for the shared database schema initialisation owner."""

from declan.core.database_schema_state import DatabaseSchemaState


class TimerSchemaState(DatabaseSchemaState):
    """Timer-specific compatibility adapter for existing importers."""
