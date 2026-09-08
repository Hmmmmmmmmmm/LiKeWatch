"""Qt desktop interface. Widgets remain on the main thread."""

import copy
import time
from pathlib import Path
import cv2
import numpy as np
from PySide6.QtCore import Qt, Signal, QTimer, QPointF, QSettings
from PySide6.QtGui import QImage, QPixmap, QPen, QColor, QPainter, QPolygonF
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QLineEdit,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QMessageBox,
    QFileDialog,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QPlainTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsEllipseItem,
    QAbstractItemView,
    QGroupBox,
    QInputDialog,
)
from platformdirs import user_data_dir
from .domain import Region, Rule, Quality
from .profiles import demo_profile, load, save, validate
from .rules import evaluate
from .imaging import validate_corners, rectify, preprocess
from .capture import demo_frame
from .storage import Store
from .runtime import MonitorWorker, DeliveryWorker
from .messaging import save_token


def pixmap(frame):
    if frame.ndim == 2:
        rgb = cv2.cvtColor(frame, cv2.COLOR_GRAY2RGB)
    else:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    rgb = np.ascontiguousarray(rgb)
    return QPixmap.fromImage(
        QImage(
            rgb.data,
            rgb.shape[1],
            rgb.shape[0],
            rgb.strides[0],
            QImage.Format.Format_RGB888,
        ).copy()
    )


def button(text, callback):
    widget = QPushButton(text)
    widget.clicked.connect(callback)
    return widget


def group(title):
    widget = QGroupBox(title)
    layout = QVBoxLayout(widget)
    return widget, layout


def spin(value, minimum, maximum, decimals=0):
    widget = QDoubleSpinBox() if decimals else QSpinBox()
    widget.setRange(minimum, maximum)
    if decimals:
        widget.setDecimals(decimals)
    widget.setValue(value)
    return widget


class Handle(QGraphicsEllipseItem):
    def __init__(self, point, callback):
        super().__init__(-6, -6, 12, 12)
        self.setPos(point)
        self.setBrush(QColor("#2dd4bf"))
        self.setPen(QPen(QColor("white"), 1))
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(self.GraphicsItemFlag.ItemIgnoresTransformations)
        self.callback = callback
        self.setZValue(10)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.callback()


class ImageView(QGraphicsView):
    corners_chosen = Signal(object)
    corners_edited = Signal(str, object)
    selected = Signal(str)

    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(self.DragMode.ScrollHandDrag)
        self.frame = None
        self.regions = []
        self.selected_id = None
        self.editable = False
        self.picking = False
        self.points = []
        self.handles = []
        self.setMinimumSize(320, 300)

    def show_frame(self, frame, regions, selected=None, fit=False):
        self.frame, self.regions, self.selected_id = frame, regions, selected
        self.scene().clear()
        self.handles = []
        self.scene().addPixmap(pixmap(frame))
        h, w = frame.shape[:2]
        self.setSceneRect(0, 0, w, h)
        for region in regions:
            points = [QPointF(x * (w - 1), y * (h - 1)) for x, y in region.corners]
            pen = QPen(QColor("#2dd4bf" if region.id == selected else "#60a5fa"), 2)
            pen.setCosmetic(True)
            polygon = self.scene().addPolygon(QPolygonF(points), pen)
            polygon.setData(0, region.id)
            label = self.scene().addText(region.name)
            label.setDefaultTextColor(QColor("#0f766e"))
            label.setPos(points[0])
            if self.editable and region.id == selected:
                for point in points:
                    handle = Handle(
                        point, lambda rid=region.id: self.handle_changed(rid)
                    )
                    self.scene().addItem(handle)
                    self.handles.append(handle)
        if fit:
            self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def handle_changed(self, region_id):
        h, w = self.frame.shape[:2]
        corners = [
            [handle.pos().x() / (w - 1), handle.pos().y() / (h - 1)]
            for handle in self.handles
        ]
        self.corners_edited.emit(region_id, corners)

    def mousePressEvent(self, event):
        if self.picking and event.button() == Qt.MouseButton.LeftButton:
            point = self.mapToScene(event.position().toPoint())
            if self.sceneRect().contains(point):
                self.points.append(point)
                self.scene().addEllipse(
                    point.x() - 4,
                    point.y() - 4,
                    8,
                    8,
                    QPen(QColor("#f59e0b")),
                    QColor("#f59e0b"),
                )
                if len(self.points) == 4:
                    h, w = self.frame.shape[:2]
                    corners = [[p.x() / (w - 1), p.y() / (h - 1)] for p in self.points]
                    self.picking = False
                    self.points = []
                    self.corners_chosen.emit(corners)
            return
        item = self.itemAt(event.position().toPoint())
        if item and item.data(0):
            self.selected.emit(item.data(0))
        super().mousePressEvent(event)

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        if 0.02 < self.transform().m11() * factor < 20:
            self.scale(factor, factor)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.frame is not None:
            self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)


class RegionDialog(QDialog):
    def __init__(self, region, parent):
        super().__init__(parent)
        self.setWindowTitle("Variable / OCR settings")
        self.region = copy.deepcopy(region)
        layout = QFormLayout(self)
        self.name = QLineEdit(region.name)
        self.kind = QComboBox()
        self.kind.addItems(["number", "text"])
        self.kind.setCurrentText(region.kind)
        self.unit = QLineEdit(region.unit)
        self.recipe = QComboBox()
        self.recipe.addItems(["gray", "invert", "otsu", "adaptive"])
        self.recipe.setCurrentText(region.preprocessing)
        self.confidence = spin(region.confidence, 0, 100)
        self.minimum = QLineEdit(region.minimum)
        self.maximum = QLineEdit(region.maximum)
        self.aspect = spin(region.aspect, 0, 20, 2)
        self.psm = QComboBox()
        self.psm.addItems(["Single line", "Single word"])
        self.psm.setCurrentIndex(region.psm - 7)
        for label, widget in [
            ("Name", self.name),
            ("Type", self.kind),
            ("Unit", self.unit),
            ("Preprocessing", self.recipe),
            ("Minimum confidence", self.confidence),
            ("Minimum (optional)", self.minimum),
            ("Maximum (optional)", self.maximum),
            ("Width / height (0 = automatic)", self.aspect),
            ("Segmentation", self.psm),
        ]:
            layout.addRow(label, widget)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def value(self):
        r = self.region
        r.name, r.kind, r.unit = (
            self.name.text().strip(),
            self.kind.currentText(),
            self.unit.text().strip(),
        )
        r.preprocessing, r.confidence = (
            self.recipe.currentText(),
            self.confidence.value(),
        )
        r.minimum, r.maximum = self.minimum.text().strip(), self.maximum.text().strip()
        r.aspect, r.psm = self.aspect.value(), self.psm.currentIndex() + 7
        return r


class ConditionEditor(QWidget):
    def __init__(self, regions, node=None):
        super().__init__()
        self.regions = regions
        layout = QVBoxLayout(self)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Condition", "Operator", "Value"])
        layout.addWidget(self.tree)
        actions = QHBoxLayout()
        actions.addWidget(button("+ Comparison", self.add_leaf))
        actions.addWidget(button("+ Group", self.add_group))
        actions.addWidget(button("Edit", self.edit))
        actions.addWidget(button("Remove", self.remove))
        layout.addLayout(actions)
        self.tree.itemDoubleClicked.connect(lambda *_: self.edit())
        self.add_node(node or {"group": "ALL", "children": []}, None)
        self.tree.expandAll()

    def add_node(self, node, parent):
        item = QTreeWidgetItem(parent if parent else self.tree)
        item.setData(0, Qt.ItemDataRole.UserRole, node)
        if "group" in node:
            item.setText(0, "AND — all" if node["group"] == "ALL" else "OR — any")
            for child in node["children"]:
                self.add_node(child, item)
        else:
            region = next((r for r in self.regions if r.id == node["variable"]), None)
            item.setText(0, region.name if region else "Missing variable")
            item.setText(1, node["op"])
            item.setText(2, node["value"])
        return item

    def parent_group(self):
        item = self.tree.currentItem() or self.tree.topLevelItem(0)
        if "group" not in item.data(0, Qt.ItemDataRole.UserRole):
            item = item.parent()
        return item

    def leaf_dialog(self, node=None):
        if not self.regions:
            return None
        dialog = QDialog(self)
        dialog.setWindowTitle("Comparison")
        layout = QFormLayout(dialog)
        variable = QComboBox()
        for region in self.regions:
            variable.addItem(region.name, region.id)
        op = QComboBox()
        op.addItems([">", ">=", "<", "<=", "==", "!="])
        value = QLineEdit("0")
        if node:
            variable.setCurrentIndex(variable.findData(node["variable"]))
            op.setCurrentText(node["op"])
            value.setText(node["value"])
        layout.addRow("Variable", variable)
        layout.addRow("Operator", op)
        layout.addRow("Value", value)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec():
            return {
                "variable": variable.currentData(),
                "op": op.currentText(),
                "value": value.text(),
            }

    def add_leaf(self):
        node = self.leaf_dialog()
        if node:
            self.add_node(node, self.parent_group())
            self.tree.expandAll()

    def add_group(self):
        choice, ok = QInputDialog.getItem(
            self, "Group", "Combine children using", ["AND", "OR"], 0, False
        )
        if ok:
            self.add_node(
                {"group": "ALL" if choice == "AND" else "ANY", "children": []},
                self.parent_group(),
            )
            self.tree.expandAll()

    def edit(self):
        item = self.tree.currentItem()
        if not item:
            return
        node = item.data(0, Qt.ItemDataRole.UserRole)
        if "group" in node:
            node["group"] = "ANY" if node["group"] == "ALL" else "ALL"
            item.setData(0, Qt.ItemDataRole.UserRole, node)
            item.setText(0, "AND — all" if node["group"] == "ALL" else "OR — any")
        else:
            replacement = self.leaf_dialog(node)
            if replacement:
                parent = item.parent()
                index = parent.indexOfChild(item)
                parent.takeChild(index)
                self.add_node(replacement, parent)

    def remove(self):
        item = self.tree.currentItem()
        if item and item.parent():
            item.parent().removeChild(item)

    def value(self, item=None):
        item = item or self.tree.topLevelItem(0)
        node = copy.deepcopy(item.data(0, Qt.ItemDataRole.UserRole))
        if "group" in node:
            node["children"] = [
                self.value(item.child(i)) for i in range(item.childCount())
            ]
        return node


class RuleDialog(QDialog):
    def __init__(self, profile, rule, parent):
        super().__init__(parent)
        self.setWindowTitle("Condition and recovery")
        self.resize(650, 650)
        self.profile, self.rule = profile, copy.deepcopy(rule)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(rule.name)
        form.addRow("Rule name", self.name)
        self.confirm = spin(rule.confirm, 1, 100)
        form.addRow("Activation samples", self.confirm)
        self.recover = spin(rule.recover_confirm, 1, 100)
        form.addRow("Recovery samples", self.recover)
        self.gap = spin(rule.max_gap, profile.interval, 86400, 1)
        form.addRow("Maximum sample gap (s)", self.gap)
        layout.addLayout(form)
        layout.addWidget(QLabel("Activate when"))
        self.condition = ConditionEditor(profile.regions, rule.condition)
        layout.addWidget(self.condition)
        self.custom = QCheckBox("Separate recovery condition (hysteresis)")
        self.custom.setChecked(rule.recovery is not None)
        layout.addWidget(self.custom)
        self.recovery = ConditionEditor(profile.regions, rule.recovery)
        layout.addWidget(self.recovery)
        self.recovery.setEnabled(self.custom.isChecked())
        self.custom.toggled.connect(self.recovery.setEnabled)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.check)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def check(self):
        try:
            self.rule.name = self.name.text().strip()
            self.rule.condition = self.condition.value()
            self.rule.recovery = (
                self.recovery.value() if self.custom.isChecked() else None
            )
            self.rule.confirm = self.confirm.value()
            self.rule.recover_confirm = self.recover.value()
            self.rule.max_gap = self.gap.value()
            candidate = copy.deepcopy(self.profile)
            candidate.rules = [r for r in candidate.rules if r.id != self.rule.id] + [
                self.rule
            ]
            validate(candidate)
            self.accept()
        except Exception as error:
            QMessageBox.warning(self, "Invalid condition", str(error))


class SettingsDialog(QDialog):
    def __init__(self, profile, parent):
        super().__init__(parent)
        self.setWindowTitle("Capture and Telegram settings")
        self.profile = copy.deepcopy(profile)
        layout = QFormLayout(self)
        self.device = spin(profile.device, 0, 100)
        self.interval = spin(profile.interval, 0.2, 3600, 1)
        self.freshness = spin(profile.freshness, 0.2, 86400, 1)
        self.chat = QLineEdit(profile.chat_id)
        self.topic = QLineEdit(profile.topic_id)
        self.token = QLineEdit()
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.setPlaceholderText(
            "Leave blank to keep token in OS credential store"
        )
        self.enabled = QCheckBox("Enable outbound messages for this session")
        self.enabled.setChecked(profile.delivery_enabled)
        self.data = spin(profile.data_interval, 0, 86400)
        for label, widget in [
            ("Camera / monitor index (screen 0 = all)", self.device),
            ("Capture interval (s)", self.interval),
            ("Freshness (s)", self.freshness),
            ("Telegram chat ID", self.chat),
            ("Topic ID (optional)", self.topic),
            ("Bot token", self.token),
            ("Delivery", self.enabled),
            ("Data interval (0 = disabled)", self.data),
        ]:
            layout.addRow(label, widget)
        self.route_boxes = {}
        for route in ["ALERT", "RECOVERY", "DATA", "SYSTEM", "TEST"]:
            box = QCheckBox(route)
            box.setChecked(route in profile.routes)
            self.route_boxes[route] = box
            layout.addRow("Send event", box)
        notice = QLabel(
            "OCR stays local. Enabled Telegram messages send readings off this device.\nTokens use Keychain / Windows Credential Locker. Profiles never contain tokens.\nEnabling delivery also resumes queued messages for this profile."
        )
        notice.setWordWrap(True)
        layout.addRow(notice)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.check)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def check(self):
        try:
            p = self.profile
            p.device = self.device.value()
            p.interval = self.interval.value()
            p.freshness = self.freshness.value()
            p.chat_id = self.chat.text().strip()
            p.topic_id = self.topic.text().strip()
            p.delivery_enabled = self.enabled.isChecked()
            p.data_interval = self.data.value()
            p.routes = [r for r, b in self.route_boxes.items() if b.isChecked()]
            validate(p)
            if p.delivery_enabled and not p.chat_id:
                raise ValueError("Set a Telegram chat ID before enabling delivery")
            save_token(p.id, self.token.text())
            self.accept()
        except Exception as error:
            QMessageBox.warning(
                self,
                "Settings not saved",
                f"{type(error).__name__}: check settings or OS credential store",
            )


class MainWindow(QMainWindow):
    def __init__(self, data_dir=None):
        super().__init__()
        self.setWindowTitle("LiKeWatch · local OCR monitor")
        self.resize(1500, 930)
        self.data_dir = Path(data_dir or user_data_dir("LiKeWatch", "LiKeWatch"))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.profile = demo_profile()
        if (self.data_dir / "last-profile.json").exists():
            try:
                self.profile = load(self.data_dir / "last-profile.json")
            except Exception:
                pass
        self.frame = demo_frame() if self.profile.source == "demo" else None
        self.observations = {}
        self.previews = {}
        self.selected_id = None
        self.busy = False
        self.revision = 0
        self.settings = QSettings("LiKeWatch", "LiKeWatch")
        self.store = Store(self.data_dir / "history.sqlite3")
        self.worker = MonitorWorker(self.store)
        self.delivery = DeliveryWorker(self.store)
        self.worker.result.connect(self.received)
        self.worker.error.connect(self.failed)
        self.worker.history.connect(self.show_history)
        self.delivery.changed.connect(self.refresh_history)
        self.build()
        self.worker.start()
        self.delivery.start()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.snapshot)
        self.age_timer = QTimer(self)
        self.age_timer.timeout.connect(self.update_values)
        self.age_timer.start(500)
        self.refresh_regions()
        self.refresh_rules()
        self.log("INFO", "Ready. Demo uses real local OCR. Select Snapshot to analyze.")
        self.worker.submit(
            (self.revision, copy.deepcopy(self.profile), "history", None)
        )
        saved = self.settings.value("splitter")
        if saved:
            self.splitter.restoreState(saved)

    def build(self):
        root = QWidget()
        outer = QVBoxLayout(root)
        self.setCentralWidget(root)
        title = QLabel("LiKeWatch  /  OBSERVE · READ · ALERT")
        title.setStyleSheet(
            "font-size:20px; font-weight:600; color:#0f766e; padding:8px;"
        )
        outer.addWidget(title)
        toolbar = QHBoxLayout()
        self.source = QComboBox()
        self.source.addItems(["demo", "camera", "screen", "image"])
        self.source.setCurrentText(self.profile.source)
        self.source.currentTextChanged.connect(self.change_source)
        toolbar.addWidget(QLabel("Source"))
        toolbar.addWidget(self.source)
        toolbar.addWidget(button("Open image", self.open_image))
        toolbar.addWidget(button("Snapshot", self.snapshot))
        self.start_button = button("Start monitoring", self.toggle)
        toolbar.addWidget(self.start_button)
        toolbar.addWidget(button("+ Region", self.add_region))
        toolbar.addWidget(button("Save profile", self.save_profile))
        toolbar.addWidget(button("Load profile", self.load_profile))
        toolbar.addWidget(button("Settings", self.open_settings))
        outer.addLayout(toolbar)
        self.banner = QLabel(
            "Paused · four corners are stored in source-image coordinates"
        )
        outer.addWidget(self.banner)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(self.splitter, 1)
        left, ll = group("01  ANALYZED IMAGE")
        self.image = ImageView()
        ll.addWidget(self.image, 1)
        self.frame_label = QLabel("No analyzed frame yet")
        ll.addWidget(self.frame_label)
        self.edit_geometry = QCheckBox("Edit corners on frozen frame")
        self.edit_geometry.toggled.connect(self.geometry_mode)
        ll.addWidget(self.edit_geometry)
        ll.addWidget(
            button(
                "Fit image",
                lambda: self.image.fitInView(
                    self.image.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio
                ),
            )
        )
        self.image.corners_chosen.connect(self.region_chosen)
        self.image.corners_edited.connect(self.region_edited)
        self.image.selected.connect(self.select_region)
        self.splitter.addWidget(left)
        middle, ml = group("02  REGIONS & VARIABLES")
        previews = QHBoxLayout()
        self.original = QLabel("Original crop")
        self.corrected = QLabel("Corrected / OCR input")
        for label in [self.original, self.corrected]:
            label.setMinimumSize(140, 130)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet("background:#e2e8f0; color:#334155; border-radius:6px;")
            previews.addWidget(label)
        ml.addLayout(previews)
        self.preprocessed = QCheckBox("Show final OCR input")
        self.preprocessed.toggled.connect(self.update_preview)
        ml.addWidget(self.preprocessed)
        self.variables = QTableWidget(0, 7)
        self.variables.setHorizontalHeaderLabels(
            ["Variable", "Value", "Unit", "Raw OCR", "Confidence", "Quality", "Age"]
        )
        self.variables.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.variables.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.variables.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.variables.itemSelectionChanged.connect(self.table_selected)
        ml.addWidget(self.variables, 1)
        row = QHBoxLayout()
        row.addWidget(button("Edit variable", self.edit_region))
        row.addWidget(button("Remove", self.remove_region))
        ml.addLayout(row)
        self.splitter.addWidget(middle)
        right, rl = group("03  CONDITIONS & ALERTS")
        self.rule_list = QTableWidget(0, 3)
        self.rule_list.setHorizontalHeaderLabels(["Rule", "State", "Result"])
        self.rule_list.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.rule_list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.rule_list.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        rl.addWidget(self.rule_list)
        row = QHBoxLayout()
        row.addWidget(button("+ Rule", self.add_rule))
        row.addWidget(button("Edit", self.edit_rule))
        row.addWidget(button("Remove", self.remove_rule))
        rl.addLayout(row)
        rl.addWidget(QLabel("Incidents and delivery · latest 100 events"))
        self.events = QTableWidget(0, 4)
        self.events.setHorizontalHeaderLabels(
            ["Time / event", "Kind", "Delivery", "Ack"]
        )
        self.events.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.events.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.events.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        rl.addWidget(self.events, 1)
        row = QHBoxLayout()
        row.addWidget(button("Acknowledge", self.acknowledge))
        row.addWidget(button("Test send", self.test_send))
        rl.addLayout(row)
        rl.addWidget(button("Retry failed / uncertain deliveries…", self.retry))
        self.splitter.addWidget(right)
        self.splitter.setSizes([600, 430, 400])
        logbar = QHBoxLayout()
        logbar.addWidget(QLabel("ACTIVITY LOG"))
        self.log_filter = QComboBox()
        self.log_filter.addItems(["All", "INFO", "ERROR"])
        logbar.addWidget(self.log_filter)
        self.pause_log = QCheckBox("Pause scrolling")
        logbar.addWidget(self.pause_log)
        logbar.addStretch()
        logbar.addWidget(button("Export logs", self.export_logs))
        outer.addLayout(logbar)
        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        self.logs.setMaximumBlockCount(1000)
        self.logs.setMaximumHeight(130)
        outer.addWidget(self.logs)
        self.setStyleSheet(
            "QGroupBox {font-weight:600; border:1px solid #cbd5e1; border-radius:7px; margin-top:12px; padding-top:12px;} QGroupBox::title {subcontrol-origin:margin; left:10px;} QPushButton {padding:6px 9px;} QTableWidget {gridline-color:#e2e8f0;}"
        )

    def log(self, level, message):
        if self.log_filter.currentText() not in ("All", level):
            return
        bar = self.logs.verticalScrollBar()
        position = bar.value()
        self.logs.appendPlainText(f"{time.strftime('%H:%M:%S')}  {level}  {message}")
        if self.pause_log.isChecked():
            bar.setValue(position)

    def stop(self):
        self.timer.stop()
        self.start_button.setText("Start monitoring")

    def invalidate(self):
        self.stop()
        self.revision += 1
        with self.worker.commit_guard:
            self.worker.revision = self.revision
        self.busy = False
        self.observations = {}
        self.previews = {}
        self.update_values()
        self.refresh_rules()
        self.delivery.profile_id = (
            self.profile.id if self.profile.delivery_enabled else None
        )
        self.banner.setText("Paused · values invalidated; take a new snapshot")
        save(self.profile, self.data_dir / "last-profile.json")

    def snapshot(self):
        if self.busy or self.image.picking or self.edit_geometry.isChecked():
            return
        self.busy = self.worker.submit(
            (self.revision, copy.deepcopy(self.profile), "capture", None)
        )
        if self.busy:
            self.banner.setText("Processing a fresh frame locally…")

    def toggle(self):
        if self.timer.isActive():
            self.stop()
            self.banner.setText(
                "Paused · values expire at the configured freshness limit"
            )
        else:
            self.edit_geometry.setChecked(False)
            self.image.picking = False
            self.timer.start(int(self.profile.interval * 1000))
            self.start_button.setText("Pause")
            self.snapshot()

    def received(self, result):
        revision, frame, observations, previews, timestamp, phases = result
        if revision != self.revision:
            return
        self.busy = False
        first = self.frame is None
        self.frame = frame
        self.observations = observations
        self.previews = previews
        self.image.show_frame(frame, self.profile.regions, self.selected_id, fit=first)
        self.frame_label.setText(
            "Analyzed " + time.strftime("%H:%M:%S", time.localtime(timestamp))
        )
        self.banner.setText(
            ("Monitoring" if self.timer.isActive() else "Snapshot complete")
            + " · local OCR · "
            + (
                "Telegram enabled"
                if self.profile.delivery_enabled
                else "delivery disabled"
            )
        )
        self.update_values()
        self.update_preview()
        for i, rule in enumerate(self.profile.rules):
            phase, truth = phases[rule.id]
            self.rule_list.setItem(i, 1, QTableWidgetItem(phase))
            self.rule_list.setItem(i, 2, QTableWidgetItem(truth))
        self.log(
            "INFO",
            f"Frame analyzed: {sum(o.quality == Quality.VALID for o in observations.values())}/{len(observations)} valid variables",
        )

    def failed(self, revision, message):
        if revision != self.revision:
            return
        self.busy = False
        self.observations = {}
        self.update_values()
        self.banner.setText("Acquisition / OCR unavailable · no current readings")
        self.log("ERROR", message)

    def refresh_regions(self):
        self.variables.setRowCount(len(self.profile.regions))
        for i, region in enumerate(self.profile.regions):
            self.variables.setItem(i, 0, QTableWidgetItem(region.name))
        if self.selected_id not in {r.id for r in self.profile.regions}:
            self.selected_id = (
                self.profile.regions[0].id if self.profile.regions else None
            )
        if self.frame is not None:
            self.image.show_frame(
                self.frame, self.profile.regions, self.selected_id, fit=True
            )
        self.update_values()
        self.update_preview()

    def update_values(self):
        now = time.time()
        for i, region in enumerate(self.profile.regions):
            obs = self.observations.get(region.id)
            valid = obs and obs.current(now, self.profile.freshness)
            quality = (
                (
                    obs.quality.value
                    if now - obs.timestamp <= self.profile.freshness
                    else "STALE"
                )
                if obs
                else "UNAVAILABLE"
            )
            values = [
                str(obs.value) if valid else "—",
                region.unit,
                obs.raw if obs else "",
                f"{obs.confidence:.0f}%" if obs else "",
                quality,
                f"{now - obs.timestamp:.1f}s" if obs else "",
            ]
            for j, text in enumerate(values, 1):
                self.variables.setItem(i, j, QTableWidgetItem(text))
        for i, rule in enumerate(self.profile.rules):
            truth = evaluate(
                rule.condition, self.observations, now, self.profile.freshness
            )
            self.rule_list.setItem(i, 2, QTableWidgetItem(truth.name))

    def select_region(self, region_id):
        self.selected_id = region_id
        if self.frame is not None:
            self.image.show_frame(self.frame, self.profile.regions, region_id)
        self.update_preview()

    def table_selected(self):
        row = self.variables.currentRow()
        if 0 <= row < len(self.profile.regions):
            self.select_region(self.profile.regions[row].id)

    def update_preview(self):
        preview = self.previews.get(self.selected_id)
        if preview:
            for label, array in [
                (self.original, preview[0]),
                (
                    self.corrected,
                    preview[2] if self.preprocessed.isChecked() else preview[1],
                ),
            ]:
                label.setPixmap(
                    pixmap(array).scaled(
                        190,
                        145,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
        else:
            self.original.setText("Original crop")
            self.corrected.setText("Corrected / OCR input")

    def geometry_mode(self, enabled):
        if enabled:
            self.invalidate()
        self.image.editable = enabled
        if self.frame is not None:
            self.image.show_frame(self.frame, self.profile.regions, self.selected_id)

    def add_region(self):
        if self.frame is None:
            QMessageBox.information(
                self, "Capture first", "Take a snapshot before selecting a region."
            )
            return
        self.edit_geometry.setChecked(False)
        self.invalidate()
        self.image.picking = True
        self.image.points = []
        self.banner.setText(
            "Click four corners: top-left → top-right → bottom-right → bottom-left. Start monitoring cancels selection."
        )

    def region_chosen(self, corners):
        try:
            validate_corners(corners)
            region = Region(f"Variable {len(self.profile.regions) + 1}", corners)
            region.source_key = self.profile.source_key()
            region.source_size = [self.frame.shape[1], self.frame.shape[0]]
            rectify(self.frame, region)
            dialog = RegionDialog(region, self)
            if dialog.exec():
                candidate = copy.deepcopy(self.profile)
                candidate.regions.append(dialog.value())
                validate(candidate)
                self.profile = candidate
                self.selected_id = region.id
                self.invalidate()
        except Exception as error:
            QMessageBox.warning(self, "Invalid region", str(error))
        self.refresh_regions()

    def region_edited(self, region_id, corners):
        try:
            validate_corners(corners)
            candidate = copy.deepcopy(self.profile)
            region = next(r for r in candidate.regions if r.id == region_id)
            region.corners = corners
            region.source_key = candidate.source_key()
            region.source_size = [self.frame.shape[1], self.frame.shape[0]]
            original, corrected = rectify(self.frame, region)
            validate(candidate)
            self.profile = candidate
            self.invalidate()
            self.previews[region_id] = (
                original,
                corrected,
                preprocess(corrected, region.preprocessing),
            )
        except Exception as error:
            QMessageBox.warning(self, "Invalid corners", str(error))
        self.refresh_regions()

    def edit_region(self):
        region = next(
            (r for r in self.profile.regions if r.id == self.selected_id), None
        )
        if not region:
            return
        self.stop()
        dialog = RegionDialog(region, self)
        if dialog.exec():
            try:
                updated = dialog.value()
                if self.frame is not None:
                    updated.source_key = self.profile.source_key()
                    updated.source_size = [self.frame.shape[1], self.frame.shape[0]]
                candidate = copy.deepcopy(self.profile)
                candidate.regions = [
                    updated if r.id == region.id else r for r in candidate.regions
                ]
                validate(candidate)
                self.profile = candidate
                self.invalidate()
                self.refresh_regions()
            except Exception as error:
                QMessageBox.warning(self, "Invalid variable", str(error))

    def remove_region(self):
        candidate = copy.deepcopy(self.profile)
        candidate.regions = [r for r in candidate.regions if r.id != self.selected_id]
        try:
            validate(candidate)
        except Exception:
            QMessageBox.warning(
                self,
                "Variable is referenced",
                "Remove or edit rules referencing this variable first.",
            )
            return
        self.profile = candidate
        self.invalidate()
        self.refresh_regions()

    def refresh_rules(self):
        if not hasattr(self, "rule_list"):
            return
        self.rule_list.setRowCount(len(self.profile.rules))
        for i, rule in enumerate(self.profile.rules):
            for j, text in enumerate([rule.name, "Awaiting sample", "UNKNOWN"]):
                self.rule_list.setItem(i, j, QTableWidgetItem(text))

    def add_rule(self):
        if not self.profile.regions:
            return
        self.stop()
        dialog = RuleDialog(
            self.profile,
            Rule(
                "New rule",
                {"group": "ALL", "children": []},
                max_gap=max(2, self.profile.interval * 2),
            ),
            self,
        )
        if dialog.exec():
            self.profile.rules.append(dialog.rule)
            self.invalidate()

    def edit_rule(self):
        row = self.rule_list.currentRow()
        if not 0 <= row < len(self.profile.rules):
            return
        self.stop()
        dialog = RuleDialog(self.profile, self.profile.rules[row], self)
        if dialog.exec():
            self.profile.rules[row] = dialog.rule
            self.invalidate()

    def remove_rule(self):
        row = self.rule_list.currentRow()
        if 0 <= row < len(self.profile.rules):
            self.profile.rules.pop(row)
            self.invalidate()

    def change_source(self, source):
        self.profile.source = source
        self.frame = None
        self.image.scene().clear()
        self.invalidate()
        self.frame_label.setText("Source changed · capture and verify region placement")

    def open_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose image", "", "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)"
        )
        if path:
            self.profile.image_path = path
            self.source.setCurrentText("image")
            self.invalidate()
            self.snapshot()

    def open_settings(self):
        self.stop()
        dialog = SettingsDialog(self.profile, self)
        if dialog.exec():
            self.profile = dialog.profile
            self.invalidate()

    def save_profile(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export profile", "LiKeWatch-profile.json", "JSON (*.json)"
        )
        if path:
            try:
                save(self.profile, path)
                self.log(
                    "INFO", "Profile saved without credentials or enabled delivery"
                )
            except Exception as error:
                QMessageBox.warning(self, "Save failed", str(error))

    def load_profile(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load profile", "", "JSON (*.json)")
        if path:
            try:
                self.profile = load(path)
                self.source.blockSignals(True)
                self.source.setCurrentText(self.profile.source)
                self.source.blockSignals(False)
                self.frame = None
                self.image.scene().clear()
                self.invalidate()
                self.refresh_regions()
                self.refresh_history()
            except Exception as error:
                QMessageBox.warning(self, "Load failed", str(error))

    def refresh_history(self):
        if not self.busy:
            self.worker.submit(
                (self.revision, copy.deepcopy(self.profile), "history", None)
            )

    def show_history(self, revision, rows):
        if revision != self.revision:
            return
        self.history_rows = rows
        self.events.setRowCount(len(rows))
        for i, row in enumerate(rows):
            texts = [
                time.strftime("%H:%M:%S", time.localtime(row["created"]))
                + " "
                + row["body"].split("\n")[0],
                row["kind"],
                row["delivery"],
                "Yes" if row["acknowledged"] else "",
            ]
            for j, text in enumerate(texts):
                item = QTableWidgetItem(text)
                item.setToolTip(row["body"] + "\n" + row["detail"])
                self.events.setItem(i, j, item)

    def acknowledge(self):
        row = self.events.currentRow()
        if 0 <= row < len(getattr(self, "history_rows", [])):
            incident = self.history_rows[row]["incident"]
            if incident:
                self.worker.submit(
                    (self.revision, copy.deepcopy(self.profile), "ack", incident)
                )

    def test_send(self):
        if not self.profile.delivery_enabled or "TEST" not in self.profile.routes:
            QMessageBox.information(
                self,
                "Delivery disabled",
                "Enable delivery and the TEST route in Settings first.",
            )
            return
        self.worker.submit((self.revision, copy.deepcopy(self.profile), "test", None))

    def retry(self):
        if (
            QMessageBox.question(
                self,
                "Retry delivery",
                "An uncertain message may already be in Telegram. Retry failed and uncertain messages? This can create duplicates.",
            )
            == QMessageBox.StandardButton.Yes
        ):
            self.worker.submit(
                (self.revision, copy.deepcopy(self.profile), "retry", None)
            )

    def export_logs(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export logs", "LiKeWatch.log", "Log (*.log)"
        )
        if path:
            Path(path).write_text(self.logs.toPlainText(), encoding="utf-8")

    def closeEvent(self, event):
        self.stop()
        self.age_timer.stop()
        self.settings.setValue("splitter", self.splitter.saveState())
        self.worker.stopping.set()
        self.delivery.stopping.set()
        self.delivery.profile_id = None
        self.banner.setText("Finishing background work…")
        if not self.worker.wait(100) or not self.delivery.wait(100):
            event.ignore()
            QTimer.singleShot(250, self.close)
            return
        save(self.profile, self.data_dir / "last-profile.json")
        event.accept()
