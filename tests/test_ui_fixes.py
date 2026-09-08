import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import time
import numpy as np
import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication
from likewatch.capture import checked_frame, composite_displays, demo_frame
from likewatch.domain import parse_observation
from likewatch.ui import MainWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def wait(app, predicate):
    deadline = time.time() + 4
    while not predicate() and time.time() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert predicate()


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    class FakeOcr:
        def analyze(self, frame, regions, timestamp, frame_id):
            return {
                r.id: parse_observation(
                    r, "83.2" if i == 0 else "18.4", 99, timestamp, frame_id
                )
                for i, r in enumerate(regions)
            }, {}

        def close(self):
            pass

    monkeypatch.setattr("likewatch.runtime.OcrSupervisor", FakeOcr)
    monkeypatch.setattr("likewatch.runtime.Capture.read", lambda *_: demo_frame())
    view = MainWindow(tmp_path)
    view.show()
    wait(app, lambda: view.worker.jobs.empty())
    yield view
    view.worker.stopping.set()
    view.delivery.stopping.set()
    assert view.worker.wait(5000)
    assert view.delivery.wait(5000)
    view.close()
    app.processEvents()


def test_snapshot_then_manual_ocr_never_creates_incident(window, app, monkeypatch):
    window.snapshot()
    wait(app, lambda: not window.busy)
    assert window.is_still and not window.observations
    frame = window.frame.copy()

    def forbidden(*_):
        raise AssertionError("Manual OCR must not acquire another image")

    monkeypatch.setattr("likewatch.runtime.Capture.read", forbidden)
    window.profile.rules[0].confirm = 1
    window.trigger_ocr()
    wait(app, lambda: not window.busy)
    assert len(window.observations) == 2
    assert np.array_equal(window.frame, frame)
    assert not window.store.active(window.profile.id)
    assert not window.store.history(window.profile.id)


def test_only_still_images_can_be_edited(window, app):
    window.toggle()
    assert window.timer.isActive()
    assert not window.add_region_button.isEnabled()
    assert not window.edit_region_button.isEnabled()
    assert not window.edit_geometry.isEnabled()
    count = len(window.profile.regions)
    window.add_region()
    window.edit_region()
    window.remove_region()
    assert len(window.profile.regions) == count
    assert window.pages.currentWidget() is window.splitter
    window.toggle()
    assert window.can_edit()
    assert window.add_region_button.isEnabled()


def test_settings_are_embedded_and_table_cells_stable(window, app):
    item = window.variables.item(0, 1)
    for _ in range(10):
        window.update_values()
    assert window.variables.item(0, 1) is item
    for _ in range(15):
        window.open_settings()
        editor = window.pages.currentWidget()
        assert editor is not window.splitter and not editor.isWindow()
        window.update_values()
        assert window.variables.item(0, 1) is item
        editor.reject()
        wait(app, lambda: window.pages.currentWidget() is window.splitter)


def test_region_removal_does_not_reenter_selection(window, app):
    window.profile.rules = []
    window.invalidate()
    window.variables.selectRow(0)
    window.remove_region()
    assert len(window.profile.regions) == 1
    assert window.variables.rowCount() == 1
    app.processEvents()
    assert window.selected_id == window.profile.regions[0].id


def test_loupe_uses_source_pixels_and_clamps_to_viewport(window, app):
    point = QPointF(100, 250)
    window.image.loupe.show_at(point)
    assert window.image.loupe.isVisible()
    expected = window.frame[250, 100]
    color = window.image.loupe.tile.pixelColor(16, 16)
    assert (color.blue(), color.green(), color.red()) == tuple(expected)
    window.image.loupe.show_at(QPointF(0, 0))
    assert window.image.loupe.pos().x() >= 0 and window.image.loupe.pos().y() >= 0


def test_blank_capture_rejected():
    with pytest.raises(RuntimeError, match="black screen"):
        checked_frame(np.zeros((20, 30, 3), np.uint8), "screen")


def test_composite_negative_origin_and_mixed_scale():
    left = np.full((20, 20, 3), 50, np.uint8)
    right = np.full((10, 10, 3), 200, np.uint8)
    monitors = [
        {"left": -10, "top": 0, "width": 10, "height": 10},
        {"left": 0, "top": 0, "width": 10, "height": 10},
    ]
    result = composite_displays([left, right], monitors)
    assert result.shape == (20, 40, 3)
    assert (result[:, :20] == 50).all() and (result[:, 20:] == 200).all()


def test_mac_capture_checks_permission_before_invoking_system(monkeypatch):
    from likewatch.capture import mac_screen

    monkeypatch.setattr("likewatch.capture.screen_permission", lambda: False)
    with pytest.raises(RuntimeError, match="permission is required"):
        mac_screen(0)


def test_nested_editor_returns_to_parent(window, app):
    window.add_rule()
    rule_editor = window.pages.currentWidget()
    rule_editor.condition.add_leaf()
    leaf_editor = window.pages.currentWidget()
    assert leaf_editor is not rule_editor and not leaf_editor.isWindow()
    leaf_editor.accept()
    wait(app, lambda: window.pages.currentWidget() is rule_editor)
    assert len(rule_editor.condition.value()["children"]) == 1
    rule_editor.reject()
    wait(app, lambda: window.pages.currentWidget() is window.splitter)


def test_diagnostic_formatter_redacts_token():
    import logging
    from likewatch.diagnostics import RedactedFormatter

    record = logging.LogRecord(
        "test",
        40,
        "test",
        1,
        "URL https://api.telegram.org/bot123:secret/sendMessage token=private",
        (),
        None,
    )
    result = RedactedFormatter().format(record)
    assert "secret" not in result and "private" not in result and "[REDACTED]" in result


def test_variable_selection_highlights_region(window, app):
    from PySide6.QtWidgets import QGraphicsPolygonItem

    window.snapshot()
    wait(app, lambda: not window.busy)
    for row in (1, 0):
        window.variables.selectRow(row)
        app.processEvents()
        selected = window.profile.regions[row].id
        assert window.selected_id == selected
        polygons = [item for item in window.image.scene().items()
                    if isinstance(item, QGraphicsPolygonItem)]
        assert len(polygons) == len(window.profile.regions)
        for polygon in polygons:
            assert polygon.pen().width() == (5 if polygon.data(0) == selected else 2)
            assert polygon.pen().isCosmetic()


def test_geometry_refresh_preserves_zoom(window, app):
    window.snapshot()
    wait(app, lambda: not window.busy)
    window.image.scale(2.4, 2.4)
    before = window.image.transform()
    window.region_edited(window.profile.regions[0].id, window.profile.regions[0].corners)
    assert window.image.transform() == before


def test_preview_always_shows_corrected_and_ocr(window):
    region = window.profile.regions[0]
    window.selected_id = region.id
    arrays = [np.full((20, 20, 3), value, np.uint8) for value in (20, 90, 180)]
    window.previews[region.id] = arrays
    window.update_preview()
    assert not hasattr(window, 'preprocessed')
    for label, value in ((window.original, 90), (window.corrected, 180)):
        assert label.pixmap().toImage().pixelColor(10, 10).red() == value


def test_delivery_toggle_is_on_main_page(window):
    window.profile.chat_id = 'test-only'
    window.delivery_toggle.setChecked(True)
    assert window.profile.delivery_enabled
    assert window.delivery.profile_id == window.profile.id
    window.delivery_toggle.setChecked(False)
    assert not window.profile.delivery_enabled
    assert window.delivery.profile_id is None
    window.open_settings()
    editor = window.pages.currentWidget()
    assert not hasattr(editor, 'enabled')
    assert all(box.toolTip() for box in editor.route_boxes.values())
    editor.reject()


def test_macos_accessibility_summary_has_no_native_cells(app):
    from PySide6.QtGui import QAccessible
    from PySide6.QtWidgets import QTableWidgetItem
    from likewatch.accessibility import install_table_workaround, TableSummary
    from likewatch.ui import StableTable

    if not install_table_workaround():
        pytest.skip('macOS 27 workaround')
    table = StableTable(1, 1)
    table.setItem(0, 0, QTableWidgetItem('14'))
    interface = QAccessible.queryAccessibleInterface(table)
    assert isinstance(interface, TableSummary)
    assert interface.childCount() == 0
    assert interface.role() == QAccessible.Role.StaticText
    for count in (0, 3, 1, 5, 0):
        table.setRowCount(count)
        app.processEvents()
        assert interface.childCount() == 0
        assert isinstance(interface.text(QAccessible.Text.Name), str)
