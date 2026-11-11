"""TK (Tesla Key) — entry point."""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from tk_app import __version__
from tk_app.config import data_dir
from tk_app.ui import theme
from tk_app.ui.main_window import MainWindow


def setup_logging() -> None:
    handler = RotatingFileHandler(data_dir() / "tk.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    # never let HTTP libraries log request headers (they would contain bearer tokens)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def main() -> int:
    setup_logging()
    if sys.platform == "win32":
        try:  # own taskbar group + icon instead of python.exe's
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TK.TeslaKey")
        except Exception:
            pass
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("TK")
    app.setApplicationDisplayName("TK — Tesla Key")
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")
    app.setStyleSheet(theme.stylesheet(theme.font_family()))
    logging.getLogger("tk").info("TK %s starting", __version__)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
