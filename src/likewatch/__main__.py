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
        return 1
    install_handlers(window.report_error)
    window.show()
    from .paths import context
    from PySide6.QtCore import QTimer
    current = context()
    if current.health_file:
        def ready():
            import json, os
            from pathlib import Path
            health = {'schema': 1, 'pid': os.getpid(), 'nonce': current.nonce,
                      'session': current.session, 'transaction': current.transaction,
                      'commit': current.commit, 'environment_id': current.environment_id,
                      'source': str(current.source_root), 'python': sys.executable,
                      'status': 'ready'}
            path = Path(current.health_file)
            temporary = path.with_suffix('.tmp')
            temporary.write_text(json.dumps(health), encoding='utf-8')
            temporary.replace(path)
        QTimer.singleShot(0, ready)
    if current.transaction:
        window.setEnabled(False)
        activation = QTimer(window)
        def activated():
            import json
            from pathlib import Path
            path = Path(current.activated_file)
            if path.is_file() and json.loads(path.read_text()).get('nonce') == current.nonce:
                current.transaction = ''
                window.setEnabled(True)
                window.update_controls()
                activation.stop()
                window.log('INFO', 'Update activated. Monitoring and delivery remain paused; review before restarting.')
        activation.timeout.connect(activated)
        activation.start(250)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
