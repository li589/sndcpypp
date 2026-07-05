"""Centralized logging configuration for sndcpy++.

Provides a rotating file handler with performance-conscious defaults.
Logging runs in parallel with the existing ``log_to_console`` callback —
it does NOT replace it.  Modules should use ``logging.getLogger(__name__)``
for diagnostic output that benefits from file persistence and level filtering.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

_DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_MAX_BYTES = 5 * 1024 * 1024  # 5 MB per file
_BACKUP_COUNT = 3  # keep 3 rotated files

_configured = False


def configure_logging(
    log_dir: str,
    *,
    level: int = logging.INFO,
    enable_console: bool = False,
) -> str | None:
    """Configure the root logger with a rotating file handler.

    Returns the log file path on success, or ``None`` if configuration
    was skipped (e.g. directory creation failed).
    """
    global _configured
    if _configured:
        return None

    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError:
        return None

    log_file = os.path.join(log_dir, "sndcpypp.log")
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    formatter = logging.Formatter(_DEFAULT_FORMAT, datefmt=_DEFAULT_DATE_FORMAT)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    root_logger.addHandler(file_handler)

    if enable_console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(level)
        root_logger.addHandler(console_handler)

    _configured = True
    return log_file


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger.  Safe to call before ``configure_logging``."""
    return logging.getLogger(name)
