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
            assert window.is_still and not window.observations
            window.trigger_ocr()
            deadline = time.time() + 40
            while window.busy and time.time() < deadline:
                app.processEvents()
                time.sleep(0.02)
            assert len(window.observations) == 2, (
                "GUI pipeline did not publish observations"
            )
            if "--ui-stress" in __import__("sys").argv:
                from PySide6.QtCore import QPointF, Qt
                from PySide6.QtTest import QTest

                for _ in range(30):
                    window.open_settings()
                    editor = window.pages.currentWidget()
                    assert not editor.isWindow()
                    app.processEvents()
                    time.sleep(0.05)
                    editor.reject()
                    app.processEvents()
                    app.processEvents()
                    assert window.pages.currentWidget() is window.splitter
                window.profile.rules = []
                window.invalidate()
                window.variables.selectRow(0)
                window.remove_region()
                app.processEvents()
                assert len(window.profile.regions) == 1
                window.edit_geometry.setChecked(True)
                app.processEvents()
                handle = window.image.handles[0]
                start = window.image.mapFromScene(handle.pos())
                end = window.image.mapFromScene(handle.pos() + QPointF(5, 5))
                QTest.mousePress(
                    window.image.viewport(), Qt.MouseButton.LeftButton, pos=start
                )
                QTest.mouseMove(window.image.viewport(), end, 30)
                app.processEvents()
                if "--screenshot" in __import__("sys").argv:
                    index = __import__("sys").argv.index("--screenshot")
                    window.grab().save(__import__("sys").argv[index + 1] + ".loupe.png")
                QTest.mouseRelease(
                    window.image.viewport(), Qt.MouseButton.LeftButton, pos=end
                )
                app.processEvents()
                app.processEvents()
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
