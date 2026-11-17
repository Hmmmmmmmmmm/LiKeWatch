"""Persistent Tesseract adapter extracted from ScoreSight's TextDetector.

Copyright (c) 2024 OCC AI. MIT; see vendor/scoresight/LICENSE.
The original API initialization / PIL SetImage / GetUTF8Text sequence is
retained; scoreboard models, UI state, and implicit text substitutions are removed.
"""

from pathlib import Path
import sys
import multiprocessing as mp
import threading
from .domain import Observation, Quality, parse_observation


from .paths import context


def resource_path(*parts):
    return context().source(*parts)


class TextDetector:
    def __init__(self):
        from tesserocr import PyTessBaseAPI, OEM

        self.api = PyTessBaseAPI(
            path=str(resource_path("assets", "tessdata")), lang="eng", oem=OEM.LSTM_ONLY
        )

    def read(self, image, region):
        from PIL import Image

        self.api.SetPageSegMode(region.psm)
        whitelist = (
            "0123456789.+-eE"
            if region.kind == "number"
            else (
                "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 .,:;!?_-/+()=%"
            )
        )
        self.api.SetVariable("tessedit_char_whitelist", whitelist)
        self.api.SetImage(Image.fromarray(image))
        return self.api.GetUTF8Text().strip(), float(self.api.MeanTextConf())

    def close(self):
        self.api.End()


def _worker(connection):
    from .diagnostics import initialize, logger
    from .imaging import rectify, preprocess

    initialize()
    detector = None
    try:
        detector = TextDetector()
        connection.send({'module': str(Path(__file__).resolve()), 'python': sys.executable,
                         'commit': context().commit, 'environment_id': context().environment_id})
        while True:
            request = connection.recv()
            if request is None:
                break
            frame, regions, timestamp, frame_id = request
            observations, previews = {}, {}
            for region in regions:
                try:
                    original, corrected = rectify(frame, region)
                    prepared = preprocess(corrected, region.preprocessing)
                    raw, confidence = detector.read(prepared, region)
                    observations[region.id] = parse_observation(
                        region, raw, confidence, timestamp, frame_id
                    )
                    previews[region.id] = (original, corrected, prepared)
                except Exception:
                    logger.exception("OCR failed for region %s", region.id)
                    observations[region.id] = Observation(
                        region.id, "", 0, Quality.OCR_ERROR, None, timestamp, frame_id
                    )
            connection.send((observations, previews))
    finally:
        if detector:
            detector.close()
        connection.close()


class OcrSupervisor:
    """One caller/frame at a time; bounded IPC waits and disposable OCR state.

    Initialization and each request have separate timeout budgets. Cleanup adds
    at most three two-second joins (terminate, kill, and the IPC thread).
    """

    def __init__(self, timeout=15):
        self.timeout = timeout
        self.process = self.connection = None
        self._io_thread = None

    def _exchange(self, operation):
        # Pipe send/recv (including pickling) can block even after poll succeeds.
        # Capture the operation's connection, never a later replacement worker's.
        finished = threading.Event()
        outcome = []

        def communicate():
            try:
                outcome.append((True, operation()))
            except BaseException as error:
                outcome.append((False, error))
            finally:
                finished.set()

        self._io_thread = threading.Thread(
            target=communicate, name="likewatch-ocr-ipc", daemon=True
        )
        try:
            self._io_thread.start()
        except BaseException:
            self._io_thread = None
            raise
        if not finished.wait(self.timeout):
            raise TimeoutError("OCR communication timed out")
        # Once finished is set the helper no longer touches the connection.
        self._io_thread = None
        succeeded, value = outcome[0]
        if not succeeded:
            raise value
        return value

    def analyze(self, frame, regions, timestamp, frame_id):
        if self._io_thread is not None:
            # A pathological serializer may survive worker termination. Do not
            # reuse its pipe or accumulate another helper on each retry.
            self.close()
        if not self.process or not self.process.is_alive():
            self.close()
            parent, child = mp.get_context("spawn").Pipe()
            self.connection = parent
            try:
                try:
                    self.process = mp.get_context("spawn").Process(
                        target=_worker, args=(child,), daemon=True
                    )
                    self.process.start()
                finally:
                    child.close()
                self.identity = self._exchange(parent.recv)
            except (EOFError, OSError, TimeoutError):
                self.close()
                raise RuntimeError('OCR worker initialization failed or timed out') from None
            except BaseException:
                self.close()
                raise

        connection = self.connection

        def request():
            connection.send((frame, regions, timestamp, frame_id))
            return connection.recv()

        try:
            return self._exchange(request)
        except (EOFError, BrokenPipeError, OSError, TimeoutError):
            self.close()
            raise RuntimeError(
                "OCR worker failed or timed out; retry the snapshot"
            ) from None
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.process:
            # A sentinel write can itself block behind an unread frame. The
            # subprocess owns no durable state; terminate without using its pipe.
            if self.process.is_alive():
                self.process.terminate()
            if self.process.pid is not None:
                self.process.join(timeout=2)
            if self.process.is_alive():
                self.process.kill()
                self.process.join(timeout=2)
            if self.process.is_alive():
                raise RuntimeError("OCR worker did not stop; retry shutdown")
            self.process.close()
            self.process = None
        if self._io_thread is not None:
            # Killing the peer releases blocked pipe operations on Windows.
            # Keep the pipe/thread tracked if user serialization still hangs.
            self._io_thread.join(timeout=2)
            if self._io_thread.is_alive():
                raise RuntimeError("OCR communication did not stop; retry shutdown")
            self._io_thread = None
        if self.connection:
            self.connection.close()
            self.connection = None
