"""Run blocking network calls off the UI thread and deliver results via Qt signals."""
from __future__ import annotations

import traceback
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

_active: set["_Task"] = set()


class _Signals(QObject):
    ok = Signal(object)
    error = Signal(object)


class _Task(QRunnable):
    def __init__(self, fn: Callable[[], Any]):
        super().__init__()
        self.fn = fn
        self.signals = _Signals()
        self.setAutoDelete(False)

    def run(self):
        try:
            result = self.fn()
        except Exception as exc:  # delivered to UI, never crashes the app
            exc.__tk_traceback__ = traceback.format_exc()
            self.signals.error.emit(exc)
        else:
            self.signals.ok.emit(result)


def run_async(fn: Callable[[], Any],
              on_ok: Callable[[Any], None] | None = None,
              on_error: Callable[[Exception], None] | None = None) -> None:
    task = _Task(fn)

    def finish():
        _active.discard(task)

    if on_ok:
        task.signals.ok.connect(on_ok)
    if on_error:
        task.signals.error.connect(on_error)
    task.signals.ok.connect(finish)
    task.signals.error.connect(finish)
    _active.add(task)
    QThreadPool.globalInstance().start(task)
