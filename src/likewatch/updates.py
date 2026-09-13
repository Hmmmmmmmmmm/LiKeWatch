"""Thin asynchronous GUI adapter; all deployment operations live in the manager."""
import json
from pathlib import Path
from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton
from . import __version__


def write_restart_request(context, transaction):
    path = Path(context.request_file)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps({'session': context.session, 'nonce': context.nonce, 'transaction': transaction}), encoding='utf-8')
    temporary.replace(path)


class UpdatesDialog(QDialog):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.transaction = None
        self.setWindowTitle('LiKeWatch updates')
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f'Application version: {__version__}'))
        self.status = QLabel('Check for a published update.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.check = QPushButton('Check for updates')
        self.prepare = QPushButton('Download and validate update')
        self.restart = QPushButton('Update and restart')
        self.close_button = QPushButton('Close')
        for control in (self.check, self.prepare, self.restart, self.close_button):
            layout.addWidget(control)
        self.check.clicked.connect(lambda: self.command('check'))
        self.prepare.clicked.connect(self.prepare_update)
        self.restart.clicked.connect(self.restart_update)
        self.close_button.clicked.connect(self.reject)
        self.prepare.setEnabled(False)
        self.restart.setEnabled(False)
        self.process = QProcess(self)
        self.process.finished.connect(self.finished_command)
        self.process.errorOccurred.connect(lambda _: self.failed('Update manager could not start.'))
        if not owner.runtime_context.install_root:
            self.check.setEnabled(False)
            self.status.setText('Source updates require a managed installation. Install the v0.3 source package; existing profiles remain available.')

    def command(self, operation, target=None):
        context = self.owner.runtime_context
        self.operation = operation
        for control in (self.check, self.prepare, self.restart, self.close_button):
            control.setEnabled(False)
        self.status.setText({'check':'Checking published releases…','prepare':'Downloading update…','validate':'Validating OCR and startup…'}[operation])
        arguments = ['-I', '-B', str(Path(context.install_root) / 'manager/manager.py'), '--root', context.install_root, operation]
        if target:
            arguments.append(target)
        self.process.start(context.manager_python, arguments)

    def prepare_update(self):
        if self.owner.timer.isActive() or self.owner.busy or any(t.isRunning() for t in self.owner.auth_tasks):
            self.status.setText('Pause monitoring and finish current work before validating an update.')
            return
        self.command('prepare')

    def failed(self, text):
        self.status.setText(text)
        self.check.setEnabled(True)
        self.close_button.setEnabled(True)

    def finished_command(self, code, _status):
        try:
            response = json.loads(bytes(self.process.readAllStandardOutput()).decode())
            if code or not response.get('ok'):
                self.failed(response.get('error', 'Update operation failed. Current version is unchanged.'))
                return
            result = response['result']
            if self.operation == 'check':
                self.status.setText(f"{result['status']}: {result['version']}\n{result.get('notes', '')}")
                self.prepare.setEnabled(result['status'] == 'update-available')
            elif self.operation == 'prepare':
                self.transaction = result['id']
                self.command('validate', self.transaction)
                return
            else:
                self.status.setText('Update validated. Restart to apply; monitoring and delivery will remain paused.')
                self.restart.setEnabled(True)
            self.check.setEnabled(True)
            self.close_button.setEnabled(True)
        except (ValueError, KeyError):
            self.failed('Update manager returned an invalid result. Current version is unchanged.')

    def restart_update(self):
        self.owner.restart_transaction = self.transaction
        self.reject()
        self.owner.close()

    def reject(self):
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.status.setText('Finish the current update check before closing this page.')
            return
        super().reject()
