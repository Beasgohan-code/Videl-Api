"""
Videl-Api Structured Logger

Provides application-wide logging with:
- JSON and console output formats
- Configurable log levels
- Request ID tracking
- Structured log records
- Rotating file output
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Optional

# Context variable for request tracing
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


class RequestIdFilter(logging.Filter):
    """Injects the current request ID into log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or "-"
        return True


class JsonFormatter(logging.Formatter):
    """Formats log records as JSON for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        # Include any extra fields passed via logger.extra
        for key, value in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "getMessage",
                "request_id",
            }:
                log_entry[key] = value
        return json.dumps(log_entry, separators=(",", ":"))


class ConsoleFormatter(logging.Formatter):
    """Colorized console formatter for development."""

    COLORS = {
        "DEBUG": "\033[36m",    # cyan
        "INFO": "\033[32m",     # green
        "WARNING": "\033[33m",  # yellow
        "ERROR": "\033[31m",    # red
        "CRITICAL": "\033[35m", # magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        level_color = self.COLORS.get(record.levelname, "")
        request_id = getattr(record, "request_id", "-")
        prefix = (
            f"{level_color}[{record.levelname}]{self.RESET} "
            f"[req:{request_id}] "
            f"{record.name}:{record.lineno} - "
        )
        message = record.getMessage()
        if record.exc_info:
            message += "\n" + self.formatException(record.exc_info)
        return prefix + message


# Global logger instance
_logger: Optional[logging.Logger] = None
_configured = False


def get_logger(name: str = "videl") -> logging.Logger:
    """Get or create a configured logger instance."""
    global _logger, _configured
    if _logger is not None:
        return _logger

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Avoid duplicate handlers if reconfigured
    if _configured and logger.handlers:
        _logger = logger
        return _logger

    log_level = os.getenv("VIDEL_LOG_LEVEL", "INFO").upper()
    logger.setLevel(getattr(logging, log_level, logging.INFO))

    log_format = os.getenv("VIDEL_LOG_FORMAT", "console").lower()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    if log_format == "json":
        console_handler.setFormatter(JsonFormatter())
    else:
        console_handler.setFormatter(ConsoleFormatter())
    console_handler.addFilter(RequestIdFilter())
    logger.addHandler(console_handler)

    # File handler (rotating)
    log_dir = os.getenv("VIDEL_LOG_DIR", "./logs")
    try:
        os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, "videl-api.log"),
            maxBytes=int(os.getenv("VIDEL_LOG_MAX_BYTES", "10485760")),  # 10 MB
            backupCount=int(os.getenv("VIDEL_LOG_BACKUP_COUNT", "5")),
        )
        file_handler.setFormatter(JsonFormatter())
        file_handler.addFilter(RequestIdFilter())
        logger.addHandler(file_handler)
    except OSError:
        # If we can't create the log directory, just log to console
        logger.warning("Could not create log directory %s, logging to console only", log_dir)

    _configured = True
    _logger = logger
    return logger


def set_request_id(request_id: Optional[str] = None) -> str:
    """Set the request ID for the current context. Returns the ID used."""
    if request_id is None:
        request_id = uuid.uuid4().hex[:12]
    request_id_var.set(request_id)
    return request_id


def clear_request_id() -> None:
    """Clear the request ID from the current context."""
    request_id_var.set(None)


def log_request(method: str, path: str, status_code: int, duration_ms: float, request_id: str) -> None:
    """Log an HTTP request with structured data."""
    logger = get_logger("videl.access")
    logger.info(
        "HTTP request",
        extra={
            "event": "http_request",
            "method": method,
            "path": path,
            "status_code": status_code,
            "duration_ms": round(duration_ms, 2),
            "request_id": request_id,
        },
    )


def log_download_event(event: str, job_id: str, user_id: int, extra: Optional[dict] = None) -> None:
    """Log a download lifecycle event."""
    logger = get_logger("videl.download")
    logger.info(
        f"Download event: {event}",
        extra={
            "event": "download_event",
            "download_event": event,
            "job_id": job_id,
            "user_id": user_id,
            **(extra or {}),
        },
    )


def log_auth_event(event: str, user_id: int, success: bool, extra: Optional[dict] = None) -> None:
    """Log an authentication event."""
    logger = get_logger("videl.auth")
    logger.info(
        f"Auth event: {event} (success={success})",
        extra={
            "event": "auth_event",
            "auth_event": event,
            "user_id": user_id,
            "success": success,
            **(extra or {}),
        },
    )


def log_error(error: Exception, context: Optional[str] = None, extra: Optional[dict] = None) -> None:
    """Log an error with context."""
    logger = get_logger("videl.error")
    logger.error(
        f"{context + ': ' if context else ''}{error}",
        exc_info=True,
        extra={
            "event": "error",
            "error_type": type(error).__name__,
            "context": context,
            **(extra or {}),
        },
    )
