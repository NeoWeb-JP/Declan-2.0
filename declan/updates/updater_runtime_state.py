"""Thread-safe owner for updater release offers and job lifecycle."""

from threading import Event, Lock

from declan.updates.update_results import UpdateJobState, UpdateStatusResult


class UpdaterRuntimeState:
    """Keep release offers, active jobs and restart signalling together."""

    def __init__(self):
        self.lock = Lock()
        self.tags = {}
        self.job = {"state": UpdateJobState.IDLE.value}
        self.restart = Event()
        self._check_generation = 0

    def status(self, enabled):
        with self.lock:
            return UpdateStatusResult({"enabled": enabled, **self.job})

    def begin_check(self):
        """Invalidate all previous offers before requesting fresh release data."""
        with self.lock:
            self._check_generation += 1
            self.tags.clear()
            return self._check_generation

    def finish_check(self, generation, tags):
        """Only the most recent check may publish its offers."""
        with self.lock:
            if generation != self._check_generation:
                return False
            self.tags.clear()
            self.tags.update(tags)
            return True

    def prerelease_versions(self):
        with self.lock:
            return [tag for tag, selection in self.tags.items()
                    if selection.get("prerelease")]

    def claim(self, version, current, include_prereleases):
        """Atomically select one offered release and reserve the update slot."""
        with self.lock:
            if UpdateStatusResult({"state": self.job["state"]}).active:
                raise ValueError("An update is already in progress.")
            if not isinstance(version, str) or version not in self.tags or version == current:
                raise ValueError("Check for updates and select a different release.")
            selection = self.tags[version]
            if selection.get("include_prereleases", False) != include_prereleases:
                raise ValueError("The release channel changed. Check for updates again.")
            self.job.pop("failed_step", None)
            self.job.update(state=UpdateJobState.INSTALLING.value, version=version)
            return dict(selection)

    def update_job(self, **fields):
        with self.lock:
            self.job.update(fields)

    def request_restart(self):
        with self.lock:
            self.job.update(state=UpdateJobState.RESTARTING.value)
            self.restart.set()
