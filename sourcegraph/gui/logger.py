from __future__ import annotations
import sys
from enum import IntEnum
from PySide6.QtCore import QDateTime
from sourcegraph.gui.theme import *


class Level(IntEnum):
    DEBUG   = 0
    INFO    = 1
    WARNING = 2
    ERROR   = 3


_COLORS = {
    Level.DEBUG:   FG_DIMMER,
    Level.INFO:    FG_DIM,
    Level.WARNING: COLOR_WARN,
    Level.ERROR:   COLOR_ERROR,
}

_LABELS = {
    Level.DEBUG:   "DEBUG",
    Level.INFO:    "INFO ",
    Level.WARNING: "WARN ",
    Level.ERROR:   "ERROR",
}


class _StreamToLog:
    """Helper to redirect sys.stdout/stderr to the logger."""
    def __init__(self, log_func):
        self.log_func = log_func

    def write(self, buf):
        for line in buf.rstrip().splitlines():
            if line.strip():
                self.log_func(line)

    def flush(self):
        pass


class AppLogger:
    """Process-wide singleton logger.

    Usage (anywhere in the codebase):
        from sourcegraph.gui.logger import log
        log.info("Node added")
        log.error(f"Type mismatch on port 'value': expected INT got '{val}'")
    """
    _sink = None           # QTextEdit
    _dock = None           # QDockWidget – shown automatically on errors
    min_level: Level = Level.DEBUG

    @classmethod
    def set_sink(cls, text_edit, dock=None) -> None:
        """Wire the logger to the console panel.  Call once from MainWindow.__init__."""
        cls._sink = text_edit
        cls._dock = dock

    def setup_redirection(self) -> None:
        """Redirect stdout and stderr to this logger."""
        sys.stdout = _StreamToLog(self.info)
        sys.stderr = _StreamToLog(self.error)

    def _emit(self, level: Level, message: str) -> None:
        if level < self.min_level:
            return

        ts    = QDateTime.currentDateTime().toString("HH:mm:ss")
        label = _LABELS[level]

        # Always print to process stdout/stderr so headless runs still work.
        stream = sys.__stderr__ if level >= Level.ERROR else sys.__stdout__
        if stream is not None:
            stream.write(f"[{ts}] {label}  {message}\n")

        # Push to the GUI console widget if available.
        if self._sink is not None:
            color = _COLORS[level]
            self._sink.append(
                f"<span style='color:{FG_DIMMER};'>[{ts}]</span> "
                f"<span style='color:{color};font-weight:bold;'>{label}</span> "
                f"<span style='color:{color};'>{message}</span>"
            )
            if level >= Level.ERROR and self._dock is not None:
                self._dock.show()

    def debug(self, msg: str)   -> None: self._emit(Level.DEBUG,   msg)
    def info(self, msg: str)    -> None: self._emit(Level.INFO,    msg)
    def warning(self, msg: str) -> None: self._emit(Level.WARNING, msg)
    def error(self, msg: str)   -> None: self._emit(Level.ERROR,   msg)


# Module-level singleton – import this object everywhere.
log = AppLogger()