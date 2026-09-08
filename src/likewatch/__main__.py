"""Desktop entry point and packaged native smoke test."""
import multiprocessing
import sys


def main():
    multiprocessing.freeze_support()
    if '--self-test' in sys.argv:
        from .selftest import run
        run()
        return
    from PySide6.QtWidgets import QApplication
    from .ui import MainWindow
    app=QApplication(sys.argv)
    app.setApplicationName('LiKeWatch'); app.setOrganizationName('LiKeWatch')
    window=MainWindow(); window.show()
    sys.exit(app.exec())


if __name__=='__main__':
    main()
