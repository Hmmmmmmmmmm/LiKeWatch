"""Nonblocking shutdown state shared by ordinary close and update handoff."""
import time


class Shutdown:
    def __init__(self, workers, timeout=45):
        self.workers = workers
        self.deadline = time.monotonic() + timeout
        for worker in workers.values():
            worker.stopping.set()

    def pending(self):
        return [name for name, worker in self.workers.items() if worker.isRunning()]

    @property
    def expired(self):
        return time.monotonic() >= self.deadline
