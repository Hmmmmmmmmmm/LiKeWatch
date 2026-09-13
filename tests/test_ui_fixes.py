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


def test_comparison_operators_follow_variable_type(window, app):
    from likewatch.ui import ConditionEditor

    window.profile.rules = []
    window.profile.regions[0].kind = 'text'
    editor = ConditionEditor(window.profile.regions)
    # Host through the real stacked-page route, including nested comparison pages.
    from PySide6.QtWidgets import QDialog, QVBoxLayout
    host = QDialog(window)
    QVBoxLayout(host).addWidget(editor)
    window.present_editor(host)
    accepted = []
    editor.leaf_dialog(accepted.append)
    dialog = window.pages.currentWidget()
    ops = lambda: [dialog.operator.itemData(i) for i in range(dialog.operator.count())]
    assert ops() == ['==', '!=', 'contains']
    dialog.operator.setCurrentIndex(dialog.operator.findData('contains'))
    dialog.threshold.setText('')
    dialog.check()
    assert 'non-empty' in dialog.validation_error.text()
    assert window.pages.currentWidget() is dialog
    dialog.variable.setCurrentIndex(1)
    assert 'contains' not in ops()
    dialog.threshold.setText('not a number')
    dialog.check()
    assert 'numeric' in dialog.validation_error.text()
    dialog.variable.setCurrentIndex(0)
    dialog.operator.setCurrentIndex(dialog.operator.findData('contains'))
    dialog.threshold.setText('14')
    dialog.check()
    wait(app, lambda: bool(accepted))
    assert accepted[0]['op'] == 'contains' and accepted[0]['value'] == '14'
    host.reject()
    wait(app, lambda: window.pages.currentWidget() is window.splitter)


def test_macos_tree_and_dropdown_use_summary(window, app):
    from likewatch.accessibility import install_table_workaround, TableSummary
    from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QComboBox
    from PySide6.QtGui import QAccessible

    if not install_table_workaround():
        pytest.skip('macOS 27 workaround')
    tree = QTreeWidget()
    tree.setColumnCount(3)
    combo = QComboBox()
    combo.addItems(['Text contains', '=='])
    for view in (tree, combo.view()):
        interface = QAccessible.queryAccessibleInterface(view)
        assert isinstance(interface, TableSummary)
        assert interface.childCount() == 0
    interface = QAccessible.queryAccessibleInterface(tree)
    for _ in range(30):
        parent = QTreeWidgetItem(tree, ['AND'])
        child = QTreeWidgetItem(parent, ['Text variable', 'contains', '14'])
        assert 'contains' in interface.text(QAccessible.Text.Name)
        tree.clear()
        app.processEvents()
        assert interface.childCount() == 0


def test_settings_autosave_and_new_controls(window,app):
    from likewatch.profiles import load
    window.open_settings()
    editor=window.pages.currentWidget()
    editor.attach.setChecked(True)
    # Avoid real alarms in tests.
    editor.chat.setText('test-chat')
    wait(app,lambda: window.profile.attach_snapshot)
    stored=load(window.data_dir/'last-profile.json')
    assert stored.attach_snapshot and stored.chat_id=='test-chat'
    assert 'TEST' not in editor.route_boxes
    assert not editor.revealed_token.isVisible()
    assert not window.age_timer.isActive()
    editor.reject()
    wait(app,lambda:window.pages.currentWidget() is window.splitter)


def test_local_alarm_acknowledges_and_stops(window,monkeypatch):
    from PySide6.QtWidgets import QApplication
    sounds=[]
    monkeypatch.setattr(QApplication,'beep',lambda:sounds.append(True))
    window.profile.local_alarm=True
    window.store.enqueue(window.profile,'ALERT','test',incident='test-alarm',rule=window.profile.rules[0])
    window.alarm_tick()
    assert sounds and window.ack_button.styleSheet()
    window.acknowledge()
    assert not window.store.pending_alarms(window.profile.id)
    assert not window.ack_button.styleSheet()


@pytest.mark.parametrize('volume,level',[(9,'WARNING'),(10,'INFO')])
def test_monitor_logs_alarm_volume(window,monkeypatch,volume,level):
    monkeypatch.setattr('likewatch.alarm.output_volume',lambda:volume)
    window.profile.local_alarm=True
    window.toggle()
    window.toggle()
    assert f'{level}  Alarm output volume: {volume}%' in window.logs.toPlainText()


def test_snapshot_failure_does_not_lose_incident(window,app,monkeypatch):
    def broken(*_):
        raise RuntimeError('render failed')
    monkeypatch.setattr('likewatch.runtime.incident_snapshot',broken)
    window.profile.attach_snapshot=True
    window.profile.delivery_enabled=True
    window.profile.chat_id='test-only'
    window.profile.rules[0].confirm=1
    window.toggle()
    wait(app,lambda: bool(window.store.active(window.profile.id)))
    window.toggle()
    assert window.store.history(window.profile.id)[0]['kind']=='ALERT'


def test_test_send_logs_and_history_update_inside_settings(window,app,monkeypatch):
    # Stop network delivery; inspect the durable queue without sending a real message.
    window.delivery.stopping.set();assert window.delivery.wait(5000)
    window.profile.delivery_enabled=True;window.profile.chat_id='123'
    window.open_settings();editor=window.pages.currentWidget()
    editor.attach.setChecked(True)
    editor.test_destination()
    wait(app,lambda:bool(window.store.history(window.profile.id)))
    wait(app,lambda:'TEST ' in window.logs.toPlainText())
    assert 'Test incident requested with snapshot' in window.logs.toPlainText()
    row=window.store.claim(window.profile.id)
    assert row['attachment'] and row['incident']
    window.store.delivered(row['seq'],'accepted',message_id=42)
    window.refresh_history()
    wait(app,lambda:'accepted' in window.logs.toPlainText())
    before=window.logs.toPlainText()
    window.show_history(window.revision,window.store.history(window.profile.id))
    assert window.logs.toPlainText()==before
    editor.reject()


def test_test_send_busy_is_visible(window,monkeypatch):
    window.profile.delivery_enabled=True
    monkeypatch.setattr(window.worker,'submit',lambda *_:False)
    window.test_send()
    assert 'Test incident not queued' in window.logs.toPlainText()
