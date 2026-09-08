"""Avoid Qt Cocoa's synthesized table cells on macOS 27.

The native bridge can retain stale table-cell pointers while accessibility clients
read a changing table. Expose a text summary instead on affected macOS versions;
visual table behavior and keyboard selection remain available.
"""
import platform
import sys

from PySide6.QtGui import QAccessible
from PySide6.QtWidgets import QAccessibleWidget

_installed = False


class TableSummary(QAccessibleWidget):
    def __init__(self, widget):
        super().__init__(widget, QAccessible.Role.StaticText)

    def childCount(self):
        return 0

    def child(self, index):
        return None

    def text(self, kind):
        if kind in (QAccessible.Text.Name, QAccessible.Text.Value):
            table = self.object()
            rows = []
            for row in range(table.rowCount()):
                cells = [table.item(row, col) for col in range(table.columnCount())]
                rows.append(", ".join(item.text() for item in cells if item is not None))
            return "\n".join(rows) or "Empty table"
        return super().text(kind)


def _factory(name, obj):
    if getattr(obj, "_likewatch_table_summary", False):
        return TableSummary(obj)
    return None


def install_table_workaround():
    global _installed
    affected = sys.platform == "darwin" and int(platform.mac_ver()[0].split('.')[0] or 0) >= 27
    if affected and not _installed:
        QAccessible.installFactory(_factory)
        _installed = True
    return affected
