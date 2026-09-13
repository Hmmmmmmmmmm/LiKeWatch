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


def watch_manager(window):
    """A private stdin pipe closes on supervisor death, without PID-reuse races."""
    import sys
    import os
    import threading
    from PySide6.QtCore import QTimer
    orphaned = threading.Event()
    descriptor = sys.stdin.fileno()
    def wait_for_eof():
        try:
            while os.read(descriptor, 4096):
                pass
        except (OSError, ValueError):
            pass
        finally:
            orphaned.set()
    threading.Thread(target=wait_for_eof, name='manager-lifetime', daemon=True).start()
    timer = QTimer(window)
    timer.timeout.connect(lambda: window.close() if orphaned.is_set() else None)
    timer.start(100)
    window.manager_watch = timer
