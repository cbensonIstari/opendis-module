import logging
import logging.handlers
import sys
from enum import StrEnum, auto


class LogLevel(StrEnum):
    CRITICAL = auto()
    ERROR = auto()
    WARNING = auto()
    INFO = auto()
    DEBUG = auto()


log_level_mapping = {
    LogLevel.DEBUG: logging.DEBUG,
    LogLevel.INFO: logging.INFO,
    LogLevel.WARNING: logging.WARNING,
    LogLevel.ERROR: logging.ERROR,
    LogLevel.CRITICAL: logging.CRITICAL,
}

FORMATTER = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")


def configure_initial_logging(name: str = "") -> None:
    logger = logging.getLogger(name)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(FORMATTER)
    logger.addHandler(console_handler)


def configure_logging(
    log_level: LogLevel,
    log_file_path: str,
    name: str = "",
) -> None:
    logger = logging.getLogger(name)
    mapped_log_level: int = log_level_mapping[log_level]
    logger.setLevel(mapped_log_level)

    file_handler = logging.handlers.RotatingFileHandler(
        log_file_path,
        maxBytes=10_000_000,
        backupCount=5,
    )
    file_handler.setLevel(mapped_log_level)
    file_handler.setFormatter(FORMATTER)
    logger.addHandler(file_handler)
