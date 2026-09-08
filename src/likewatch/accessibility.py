"""Avoid Qt Cocoa's synthesized table cells on macOS 27.

The native bridge can retain stale table-cell pointers while accessibility clients
read a changing table, tree, or dropdown list. Expose a text summary instead on affected macOS versions;
visual table behavior and keyboard selection remain available.
"""
import platform
import sys

from PySide6.QtGui import QAccessible
from PySide6.QtWidgets import QAccessibleWidget, QAbstractItemView
from PySide6.QtCore import QModelIndex

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
            model = self.object().model()
            rows = []

            def visit(parent=QModelIndex(), depth=0):
                if model is None or depth > 16:
                    return
                for row in range(model.rowCount(parent)):
                    if len(rows) >= 256:
                        return
                    cells = [model.index(row, col, parent).data()
                             for col in range(model.columnCount(parent))]
                    rows.append(", ".join(str(cell) for cell in cells if cell is not None))
                    visit(model.index(row, 0, parent), depth + 1)

            visit()
            return "\n".join(rows) or "Empty table"
        return super().text(kind)


def _factory(name, obj):
    if isinstance(obj, QAbstractItemView):
        return TableSummary(obj)
    return None


def install_table_workaround():
    global _installed
    affected = sys.platform == "darwin" and int(platform.mac_ver()[0].split('.')[0] or 0) >= 27
    if affected and not _installed:
        QAccessible.installFactory(_factory)
        _installed = True
    return affected
