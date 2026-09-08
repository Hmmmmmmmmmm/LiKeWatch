"""Persistent diagnostics for recoverable errors and fatal native faults."""

import faulthandler
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import sys
import threading
import tempfile
from platformdirs import user_log_dir

logger = logging.getLogger("likewatch")
_fault_file = None


class RedactedFormatter(logging.Formatter):
    def format(self, record):
        text = super().format(record)
        text = re.sub(r"bot\d+:[A-Za-z0-9_-]+", "bot[REDACTED]", text)
        return re.sub(r"(?i)(token[=:]\s*)\S+", r"\1[REDACTED]", text)


def initialize(directory=None):
    global _fault_file
    directory = Path(
        directory
        or os.environ.get("LIKEWATCH_LOG_DIR")
        or user_log_dir("LiKeWatch", "LiKeWatch")
    )
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError:
        directory = Path(tempfile.gettempdir()) / "LiKeWatch-logs"
        directory.mkdir(parents=True, exist_ok=True)
    if not logger.handlers:
        handler = RotatingFileHandler(
            directory / "application.log",
            maxBytes=2_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(
            RedactedFormatter("%(asctime)s %(levelname)s %(threadName)s %(message)s")
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    if _fault_file is None:
        _fault_file = (directory / f"native-{os.getpid()}.log").open("a", buffering=1)
        faulthandler.enable(file=_fault_file, all_threads=True)
    logger.info(
        "Application starting; Python %s; platform %s",
        sys.version.split()[0],
        sys.platform,
    )
    return directory


def install_handlers(on_error=None):
    def exception_hook(kind, value, traceback):
        if issubclass(kind, KeyboardInterrupt):
            return sys.__excepthook__(kind, value, traceback)
        logger.error("Unhandled Python exception", exc_info=(kind, value, traceback))
        if on_error:
            on_error(
                "An operation failed. Monitoring paused; details saved in the error log."
            )

    sys.excepthook = exception_hook
    threading.excepthook = lambda args: logger.error(
        "Background thread exception",
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )
    from PySide6.QtCore import qInstallMessageHandler, QtMsgType

    def qt_message(kind, context, message):
        level = (
            logging.ERROR
            if kind in (QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg)
            else logging.WARNING
        )
        logger.log(level, "Qt: %s", message)

    qInstallMessageHandler(qt_message)
