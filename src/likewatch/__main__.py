"""Desktop entry point and packaged native smoke test."""

import multiprocessing
import sys


def main():
    multiprocessing.freeze_support()
    if "--self-test" in sys.argv:
        from .selftest import run

        run()
        return
    from .diagnostics import initialize, install_handlers

    initialize()
    install_handlers()
    from PySide6.QtWidgets import QApplication, QMessageBox
    from .ui import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("LiKeWatch")
    app.setOrganizationName("LiKeWatch")
    try:
        window = MainWindow()
    except Exception as error:
        from .diagnostics import logger

        logger.exception("Application startup failed")
        message = QMessageBox()
        message.setWindowTitle("LiKeWatch could not start")
        message.setText(str(error))
        message.finished.connect(app.quit)
        message.open()
        app.exec()
        return
    install_handlers(window.report_error)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
