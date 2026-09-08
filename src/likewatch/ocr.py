"""Persistent Tesseract adapter extracted from ScoreSight's TextDetector.

Copyright (c) 2024 OCC AI. MIT; see vendor/scoresight/LICENSE.
The original API initialization / PIL SetImage / GetUTF8Text sequence is
retained; scoreboard models, UI state, and implicit text substitutions are removed.
"""

from pathlib import Path
import sys
import multiprocessing as mp
from .domain import Observation, Quality, parse_observation
from .imaging import rectify, preprocess


def resource_path(*parts):
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return root.joinpath(*parts)


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

    initialize()
    detector = None
    try:
        detector = TextDetector()
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
    """One in-flight frame, bounded timeout, restart after native crash/hang."""

    def __init__(self, timeout=15):
        self.timeout = timeout
        self.process = self.connection = None

    def analyze(self, frame, regions, timestamp, frame_id):
        if not self.process or not self.process.is_alive():
            self.close()
            parent, child = mp.get_context("spawn").Pipe()
            self.connection = parent
            self.process = mp.get_context("spawn").Process(
                target=_worker, args=(child,), daemon=True
            )
            self.process.start()
            child.close()
        try:
            self.connection.send((frame, regions, timestamp, frame_id))
            if not self.connection.poll(self.timeout):
                raise TimeoutError("OCR timed out; worker will restart")
            return self.connection.recv()
        except (EOFError, BrokenPipeError, OSError, TimeoutError):
            self.close()
            raise RuntimeError(
                "OCR worker failed or timed out; retry the snapshot"
            ) from None

    def close(self):
        if self.process:
            if self.process.is_alive():
                self.process.terminate()
            self.process.join(timeout=2)
            if self.process.is_alive():
                self.process.kill()
                self.process.join(timeout=2)
            self.process.close()
        if self.connection:
            self.connection.close()
        self.process = self.connection = None
