"""Thread-safe ownership of the timer database schema initialisation cache."""

from threading import Lock


class TimerSchemaState:
    """Only mark a database initialised after schema creation succeeds."""

    def __init__(self):
        self._lock = Lock()
        self._initialized = set()

    def ensure(self, path, create_schema):
        """Initialise a database path once per file identity.

        Run the callback while holding the lock, ensuring concurrent callers
        cannot observe an incompletely initialised schema. A replaced database
        file is initialised again because its inode changes.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            identity = (path.resolve(), path.stat().st_ino) if path.exists() else None
            if identity in self._initialized:
                return
            create_schema()
            self._initialized.add((path.resolve(), path.stat().st_ino))
