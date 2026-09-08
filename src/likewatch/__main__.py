"""Desktop entry point and packaged native smoke test."""

import multiprocessing
import sys


def main():
    multiprocessing.freeze_support()
    if "--self-test" in sys.argv:
        from .selftest import run

        run()
        return
    from PySide6.QtWidgets import QApplication, QMessageBox
    from .ui import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("LiKeWatch")
    app.setOrganizationName("LiKeWatch")
    try:
        window = MainWindow()
    except RuntimeError as error:
        QMessageBox.information(None, "LiKeWatch", str(error))
        return
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
