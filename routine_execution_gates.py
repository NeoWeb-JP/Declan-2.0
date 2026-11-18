"""Owner of concurrency guards for mapped Home Assistant routines."""
from threading import Lock


class RoutineExecutionGates:
    """Keep independent non-blocking gates for each routine/room."""

    def __init__(self):
        self._routine_locks = {
            name: Lock() for name in ("morning", "night", "movie", "movie_bedroom")
        }
        self._sexy_time_lock = Lock()

    def for_routine(self, period, *, movie_action=None, movie_room="lounge"):
        key = "movie_bedroom" if movie_action and movie_room == "bedroom" else period
        return self._routine_locks[key]

    @property
    def sexy_time(self):
        return self._sexy_time_lock
