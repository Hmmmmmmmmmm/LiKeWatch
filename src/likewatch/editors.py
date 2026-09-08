"""Non-blocking editors; main-window pages avoid nested native dialog loops."""

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QDialogButtonBox,
    QFileDialog,
)
from PySide6.QtCore import Qt


def present(parent, dialog, accepted=None):
    window = parent.window()
    if hasattr(window, "present_editor"):
        window.present_editor(dialog, accepted)
    else:
        # Used when a component is hosted independently. Keep a Python owner.
        parent._open_dialog = dialog
        if accepted:
            dialog.accepted.connect(accepted)
        dialog.open()


def notice(parent, title, text):
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    layout = QVBoxLayout(dialog)
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    layout.addWidget(label)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
    buttons.accepted.connect(dialog.accept)
    layout.addWidget(buttons)
    present(parent, dialog)


def confirm(parent, title, text, accepted):
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    layout = QVBoxLayout(dialog)
    label = QLabel(text)
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.PlainText)
    layout.addWidget(label)
    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.Cancel
    )
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    present(parent, dialog, accepted)


def choose_file(parent, title, pattern, accepted, save=False, suggested=""):
    dialog = QFileDialog(parent, title)
    dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
    dialog.setNameFilter(pattern)
    dialog.setAcceptMode(
        QFileDialog.AcceptMode.AcceptSave if save else QFileDialog.AcceptMode.AcceptOpen
    )
    dialog.setFileMode(
        QFileDialog.FileMode.AnyFile if save else QFileDialog.FileMode.ExistingFile
    )
    if suggested:
        dialog.selectFile(suggested)
    present(parent, dialog, lambda: accepted(dialog.selectedFiles()[0]))
