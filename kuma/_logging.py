import logging
import os
from typing import Optional


def configure_logging(
    level: Optional[int] = None,
    log_file: Optional[str] = None,
    format: str = "%(asctime)s|%(name)s|%(levelname)s|%(message)s",
) -> logging.Logger:
    """
    Return the legacy library logger without configuring application logging.

    With no arguments, preserve the application's logging configuration. Explicit
    options affect only ``kuma._logging``; root and dependency loggers are untouched.
    Args:
        level: Optional level for this logger; None preserves its current level
        log_file: Optional library-only log file; reuse an existing file handler
        format: Format for a newly created file handler
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(__name__)
    if level is not None:
        logger.setLevel(level)
    if log_file:
        filename = os.path.normcase(os.path.abspath(log_file))
        if not any(
            isinstance(handler, logging.FileHandler)
            and os.path.normcase(handler.baseFilename) == filename
            for handler in logger.handlers
        ):
            formatter = logging.Formatter(format)
            handler = logging.FileHandler(log_file, encoding="utf-8")
            handler.setFormatter(formatter)
            logger.addHandler(handler)
    return logger
