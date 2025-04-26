import logging
from typing import Optional


def configure_logging(
    level: int = logging.WARNING,
    log_file: Optional[str] = None,
    format: str = "%(asctime)s|%(name)s|%(levelname)s|%(message)s",
) -> logging.Logger:
    """
    Configure basic logging for the application.
    Args:
        level: Logging level (default: WARNING)
        log_file: Optional file path for logging
        format: Log message format
    Returns:
        Configured logger instance
    """
    handlers = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    logging.basicConfig(level=level, format=format, handlers=handlers)

    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)

    return logging.getLogger(__name__)
