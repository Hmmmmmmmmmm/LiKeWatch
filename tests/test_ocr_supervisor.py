"""Real spawn/pipe lifecycle tests; no Qt, images, Tesseract, or networking."""
import functools
import multiprocessing as mp
import os
import threading
import time
import unittest
from unittest.mock import patch

from likewatch import ocr


def _decode_later(delay, value):
    time.sleep(delay)
    return value


class SlowValue:
    def __init__(self, delay, value):
        self.delay, self.value = delay, value

    def __reduce__(self):
        return _decode_later, (self.delay, self.value)


def _fixture_worker(connection, mode="echo"):
    """Protocol peer, deliberately hung/crashed only when a test requests it."""
    try:
        if mode == "init_hang":
            time.sleep(30)
            return
        if mode == "init_eof":
            return
        identity = {"pid": os.getpid(), "fixture": True}
        connection.send(SlowValue(0.5, identity) if mode == "slow_identity" else identity)
        if mode == "unread":
            time.sleep(30)
            return
        while True:
            request = connection.recv()
            if request is None:
                return
            frame, regions, timestamp, frame_id = request
            if mode == "no_reply":
                time.sleep(30)
                return
            if mode == "crash":
                os._exit(7)
            if mode == "bad_reply":
                connection.send_bytes(b"not a pickle")
                continue
            result = ({"frame_id": frame_id, "pid": os.getpid()}, frame)
            if isinstance(frame, dict) and "decode_delay" in frame:
                connection.send(SlowValue(frame["decode_delay"], result))
            else:
                connection.send(result)
            if mode == "one_then_hang":
                time.sleep(30)
                return
    finally:
        connection.close()


class OcrSupervisorTests(unittest.TestCase):
    def setUp(self):
        self.engine = ocr.OcrSupervisor(timeout=2)
        self.initial_children = {child.pid for child in mp.active_children()}

    def tearDown(self):
        self.engine.close()
        self.engine.close()  # Idempotent, including after failed initialization.
        self.assertIsNone(self.engine.process)
        self.assertIsNone(self.engine.connection)
        self.assertFalse({child.pid for child in mp.active_children()} - self.initial_children)
        self.assertFalse(any(t.name == "likewatch-ocr-ipc" for t in threading.enumerate()))

    def peer(self, mode="echo"):
        return patch.object(ocr, "_worker", functools.partial(_fixture_worker, mode=mode))

    def bounded(self, operation, seconds=5):
        """Fail safely against regressions that block before reaching the timeout."""
        done = threading.Event()
        result = []

        def call():
            try:
                result.append((True, operation()))
            except BaseException as error:
                result.append((False, error))
            finally:
                done.set()

        caller = threading.Thread(target=call, daemon=True)
        caller.start()
        completed = done.wait(seconds)
        if not completed:
            # Test watchdog, independent of the supervisor's possibly broken close.
            process = self.engine.process
            if process is not None and process.is_alive():
                process.terminate()
            self.assertTrue(done.wait(3), "Watchdog could not release pipe operation")
        caller.join(1)
        self.assertTrue(completed, "OCR operation exceeded the test deadline")
        succeeded, value = result[0]
        if not succeeded:
            raise value
        return value

    def test_persistent_worker_round_trip_and_restart_after_close(self):
        with self.peer():
            result = self.bounded(lambda: self.engine.analyze(b"first", [], 1, 1))
            first_pid = self.engine.identity["pid"]
            self.assertEqual(result, ({"frame_id": 1, "pid": first_pid}, b"first"))
            frame = b"x" * (2 * 1024 * 1024)
            result = self.bounded(lambda: self.engine.analyze(frame, [], 2, 2))
            self.assertEqual(result, ({"frame_id": 2, "pid": first_pid}, frame))
            old_process = self.engine.process
            self.bounded(self.engine.close)
            self.assertTrue(old_process._closed)
            result = self.bounded(lambda: self.engine.analyze(b"restart", [], 3, 3))
            self.assertEqual(result[0]["frame_id"], 3)
            self.assertEqual(result[1], b"restart")
            self.assertIsNot(self.engine.process, old_process)

    def test_unread_request_times_out_and_reaps_worker(self):
        self.engine.timeout = 1
        with self.peer("unread"):
            # Far larger than the native pipe buffer: send itself must block.
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                self.bounded(lambda: self.engine.analyze(b"x" * (8 * 1024 * 1024), [], 1, 1), 4)
        self.assertIsNone(self.engine.process)
        with self.peer():
            self.assertEqual(self.bounded(lambda: self.engine.analyze(b"new", [], 2, 2))[1], b"new")

    def test_missing_response_times_out(self):
        self.engine.timeout = 0.5
        with self.peer("no_reply"), self.assertRaisesRegex(RuntimeError, "timed out"):
            self.bounded(lambda: self.engine.analyze(b"frame", [], 1, 1))

    def test_missing_identity_times_out(self):
        self.engine.timeout = 0.5
        with self.peer("init_hang"), self.assertRaisesRegex(RuntimeError, "initialization.*timed out"):
            self.bounded(lambda: self.engine.analyze(b"frame", [], 1, 1))

    def test_identity_deserialization_has_a_deadline(self):
        self.engine.timeout = 0.3
        with self.peer("slow_identity"), self.assertRaisesRegex(RuntimeError, "initialization.*timed out"):
            self.bounded(lambda: self.engine.analyze(b"frame", [], 1, 1))

    def test_response_deserialization_timeout_cannot_return_stale_result(self):
        with self.peer():
            self.bounded(lambda: self.engine.analyze(b"ready", [], 0, 0))
            self.engine.timeout = 0.1
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                self.bounded(lambda: self.engine.analyze({"decode_delay": 0.5}, [], 1, 1))
            self.engine.timeout = 2
            result = self.bounded(lambda: self.engine.analyze(b"fresh", [], 2, 2))
            self.assertEqual(result[0]["frame_id"], 2)
            self.assertEqual(result[1], b"fresh")

    def test_initialization_eof_and_retry(self):
        with self.peer("init_eof"), self.assertRaisesRegex(RuntimeError, "initialization"):
            self.bounded(lambda: self.engine.analyze(b"frame", [], 1, 1))
        with self.peer():
            self.assertEqual(self.bounded(lambda: self.engine.analyze(b"retry", [], 2, 2))[1], b"retry")

    def test_worker_crash_and_retry(self):
        with self.peer("crash"), self.assertRaisesRegex(RuntimeError, "failed"):
            self.bounded(lambda: self.engine.analyze(b"frame", [], 1, 1))
        with self.peer():
            self.assertEqual(self.bounded(lambda: self.engine.analyze(b"retry", [], 2, 2))[1], b"retry")

    def test_bad_response_cleans_up(self):
        import pickle
        with self.peer("bad_reply"), self.assertRaises(pickle.UnpicklingError):
            self.bounded(lambda: self.engine.analyze(b"frame", [], 1, 1))
        self.assertIsNone(self.engine.process)

    def test_shutdown_does_not_wait_for_unresponsive_peer(self):
        with self.peer("one_then_hang"):
            self.bounded(lambda: self.engine.analyze(b"ready", [], 1, 1))
            self.bounded(self.engine.close, 1.5)

    def test_stuck_serializer_does_not_accumulate_helpers_or_workers(self):
        entered, release = threading.Event(), threading.Event()

        class StuckFrame:
            def __reduce__(self):
                entered.set()
                release.wait(15)
                return bytes, (b"released",)

        try:
            with self.peer():
                self.bounded(lambda: self.engine.analyze(b"ready", [], 0, 0))
                self.engine.timeout = 0.1
                with self.assertRaisesRegex(RuntimeError, "communication did not stop"):
                    self.bounded(lambda: self.engine.analyze(StuckFrame(), [], 1, 1))
                self.assertTrue(entered.is_set())
                stuck = self.engine._io_thread
                self.assertTrue(stuck.is_alive())
                self.assertIsNone(self.engine.process)
                with patch.object(ocr.mp, "get_context") as spawn:
                    with self.assertRaisesRegex(RuntimeError, "communication did not stop"):
                        self.bounded(lambda: self.engine.analyze(b"retry", [], 2, 2))
                    spawn.assert_not_called()
                self.assertIs(self.engine._io_thread, stuck)
        finally:
            release.set()
            self.engine.close()

    def test_failed_process_start_closes_both_pipe_ends(self):
        real_context = mp.get_context("spawn")
        parent, child = real_context.Pipe()
        process = real_context.Process(target=_fixture_worker, args=(child,))
        with patch.object(ocr.mp, "get_context") as context:
            context.return_value.Pipe.return_value = parent, child
            context.return_value.Process.return_value = process
            with patch.object(process, "start", side_effect=OSError("spawn failed")):
                with self.assertRaisesRegex(RuntimeError, "initialization"):
                    self.engine.analyze(b"frame", [], 1, 1)
        self.assertTrue(parent.closed and child.closed)
        self.assertTrue(process._closed)

    def test_failed_ipc_thread_start_cleans_up_worker(self):
        with self.peer():
            self.bounded(lambda: self.engine.analyze(b"ready", [], 0, 0))
            with patch.object(ocr.threading.Thread, "start", side_effect=RuntimeError("thread unavailable")):
                with self.assertRaisesRegex(RuntimeError, "thread unavailable"):
                    self.engine.analyze(b"frame", [], 1, 1)
        self.assertIsNone(self.engine.process)
        self.assertIsNone(self.engine.connection)

    def test_failed_process_construction_closes_both_pipe_ends(self):
        parent, child = mp.get_context("spawn").Pipe()
        try:
            with patch.object(ocr.mp, "get_context") as context:
                context.return_value.Pipe.return_value = parent, child
                context.return_value.Process.side_effect = OSError("process unavailable")
                with self.assertRaises((OSError, RuntimeError)):
                    self.engine.analyze(b"frame", [], 1, 1)
            self.assertTrue(parent.closed and child.closed)
            self.assertIsNone(self.engine.connection)
        finally:
            child.close()
        with self.peer():
            self.assertEqual(self.bounded(lambda: self.engine.analyze(b"retry", [], 2, 2))[1], b"retry")


if __name__ == "__main__":
    unittest.main(verbosity=2)
