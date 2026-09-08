"""Pixel-accurate cursor loupe painted inside the image viewport."""

import cv2
import numpy as np
from PySide6.QtCore import Qt, QRect, QPointF
from PySide6.QtGui import QPainter, QColor, QImage, QPen
from PySide6.QtWidgets import QWidget


class Magnifier(QWidget):
    def __init__(self, view):
        super().__init__(view.viewport())
        self.view = view
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFixedSize(174, 198)
        self.tile = None
        self.coordinates = (0, 0)
        self.hide()

    def show_at(self, point):
        frame = self.view.frame
        if frame is None:
            return
        h, w = frame.shape[:2]
        x = max(0, min(w - 1, round(point.x())))
        y = max(0, min(h - 1, round(point.y())))
        tile = np.zeros((33, 33, 3), dtype=np.uint8)
        x0, x1 = max(0, x - 16), min(w, x + 17)
        y0, y1 = max(0, y - 16), min(h, y + 17)
        tile[y0 - y + 16 : y1 - y + 16, x0 - x + 16 : x1 - x + 16] = frame[y0:y1, x0:x1]
        rgb = np.ascontiguousarray(cv2.cvtColor(tile, cv2.COLOR_BGR2RGB))
        self.tile = QImage(
            rgb.data, 33, 33, rgb.strides[0], QImage.Format.Format_RGB888
        ).copy()
        self.coordinates = x, y
        cursor = self.view.mapFromScene(QPointF(x, y))
        px = cursor.x() + 24
        py = cursor.y() + 24
        if px + self.width() > self.parentWidget().width():
            px = cursor.x() - self.width() - 24
        if py + self.height() > self.parentWidget().height():
            py = cursor.y() - self.height() - 24
        self.move(max(0, px), max(0, py))
        self.show()
        self.raise_()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#0f172a"))
        if self.tile:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            painter.drawImage(QRect(5, 5, 165, 165), self.tile)
        painter.setPen(QPen(QColor("#ef4444"), 1))
        painter.drawLine(87, 5, 87, 170)
        painter.drawLine(5, 87, 170, 87)
        painter.setPen(QColor("white"))
        painter.drawText(
            QRect(5, 173, 165, 22),
            Qt.AlignmentFlag.AlignCenter,
            f"{self.coordinates[0]}, {self.coordinates[1]} · 5×",
        )
