"""Logging configuration for the chatbot system."""

import logging
import logging.handlers
import sys
from pathlib import Path


class SafeConsoleHandler(logging.StreamHandler):
    """Console handler that tolerates non-UTF8 Windows consoles."""

    def __init__(self, stream=None):
        super().__init__(stream or sys.stderr)
        self._configure_stream()

    def _configure_stream(self) -> None:
        stream = self.stream
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="backslashreplace")
            except Exception:
                pass

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
            stream = self.stream
            stream.write(message + self.terminator)
            self.flush()
        except UnicodeEncodeError:
            self._emit_with_safe_encoding(record)
        except Exception:
            self.handleError(record)

    def _emit_with_safe_encoding(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record) + self.terminator
            stream = self.stream
            encoding = getattr(stream, "encoding", None) or "utf-8"
            if hasattr(stream, "buffer"):
                stream.buffer.write(message.encode(encoding, errors="backslashreplace"))
            else:
                stream.write(message.encode("ascii", errors="backslashreplace").decode("ascii"))
            self.flush()
        except Exception:
            self.handleError(record)


def setup_logger(name: str) -> logging.Logger:
    """Setup logger with both console and file handlers"""

    # Configure the *root* logger so all module loggers get consistent formatting.
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    console_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
    )

    # Replace non-file stream handlers so Unicode logging is safe on Windows.
    for h in list(root.handlers):
        if isinstance(h, logging.StreamHandler) and not isinstance(
            h, logging.handlers.RotatingFileHandler
        ):
            root.removeHandler(h)

    console_handler = SafeConsoleHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_format)
    root.addHandler(console_handler)

    # Ensure a rotating file handler exists for ./logs/chatbot.log
    log_file = Path("./logs/chatbot.log")
    log_file.parent.mkdir(parents=True, exist_ok=True)

    has_file = False
    for h in list(root.handlers):
        if isinstance(h, logging.handlers.RotatingFileHandler):
            try:
                if Path(getattr(h, "baseFilename", "")).resolve() == log_file.resolve():
                    has_file = True
                    h.setLevel(logging.DEBUG)
                    h.setFormatter(file_format)
            except Exception:
                continue

    if not has_file:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=10485760, backupCount=5
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(file_format)
        root.addHandler(file_handler)

    # Return a named logger that propagates to root.
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = True
    return logger
