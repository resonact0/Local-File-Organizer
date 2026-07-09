"""Centralized logging configuration.

Replaces the old pattern of threading `silent`/`log_file` through every
function and manually branching between `print(...)` and file writes. Call
`configure_logging()` once at startup; every other module just does
`logger = get_logger(__name__)` and logs normally.
"""

import datetime
import logging
import os
import sys

LOGGER_NAME = "file_organizer"


def _unique_log_path(log_dir):
    """Pick a timestamped log file path for this run, avoiding same-second collisions."""
    os.makedirs(log_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(log_dir, f"run_{stamp}.log")
    counter = 1
    while os.path.exists(path):
        path = os.path.join(log_dir, f"run_{stamp}_{counter}.log")
        counter += 1
    return path


def configure_logging(silent: bool = False, log_dir: str = "logs") -> str:
    """Configure the shared application logger for a single run.

    Every run gets its own timestamped log file under `log_dir`, which always
    captures full DEBUG-level detail regardless of mode. When not silent,
    INFO+ messages are also printed to the terminal. Returns the path to this
    run's log file.
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    log_path = _unique_log_path(log_dir)
    file_handler = logging.FileHandler(log_path)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if not silent:
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(logging.INFO)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    return log_path


def get_logger(name: str = None) -> logging.Logger:
    """Return a child logger under the shared application logger namespace."""
    return logging.getLogger(LOGGER_NAME if not name else f"{LOGGER_NAME}.{name}")
