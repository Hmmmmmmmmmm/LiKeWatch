"""Real OCR smoke check usable inside a frozen executable."""

import json
import os
import tempfile
import time
from pathlib import Path
from decimal import Decimal


def run():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from .capture import demo_frame
    from .profiles import demo_profile
    from .ocr import OcrSupervisor
    from .domain import Quality
    from .ui import MainWindow

    app = QApplication.instance() or QApplication([])
    profile = demo_profile()
    engine = OcrSupervisor(timeout=40)
    try:
        observations, previews = engine.analyze(
            demo_frame(), profile.regions, time.time(), 1
        )
        values = [observations[r.id].value for r in profile.regions]
        assert values == [Decimal("83.2"), Decimal("18.4")], repr(observations)
        assert all(o.quality == Quality.VALID for o in observations.values())
        with tempfile.TemporaryDirectory() as directory:
            window = MainWindow(directory)
            window.show()
            app.processEvents()
            window.snapshot()
            deadline = time.time() + 40
            while window.busy and time.time() < deadline:
                app.processEvents()
                time.sleep(0.02)
            assert len(window.observations) == 2, (
                "GUI pipeline did not publish observations"
            )
            if "--screenshot" in __import__("sys").argv:
                index = __import__("sys").argv.index("--screenshot")
                window.grab().save(__import__("sys").argv[index + 1])
            window.worker.stopping.set()
            window.delivery.stopping.set()
            assert window.worker.wait(5000)
            assert window.delivery.wait(15000)
            window.close()
            app.processEvents()
        result = {
            "status": "passed",
            "engine": "Tesseract English",
            "values": [str(v) for v in values],
            "gui": "passed",
        }
        if "--report" in __import__("sys").argv:
            index = __import__("sys").argv.index("--report")
            Path(__import__("sys").argv[index + 1]).write_text(
                json.dumps(result), encoding="utf-8"
            )
        print(json.dumps(result))
    finally:
        engine.close()
