"""Logging configuration and utility functions."""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any


class JsonFormatter(logging.Formatter):
    """JSON log formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "module": record.module,
            "message": record.getMessage(),
        }

        # Add optional fields if present
        if hasattr(record, "step_id"):
            log_data["step_id"] = record.step_id
        if hasattr(record, "workflow_id"):
            log_data["workflow_id"] = record.workflow_id

        return json.dumps(log_data)


class TextFormatter(logging.Formatter):
    """Human-readable log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        parts = [self.formatTime(record), record.levelname, record.module]
        if hasattr(record, "step_id"):
            parts.append(f"[{record.step_id}]")
        parts.append(record.getMessage())
        return " ".join(parts)


def get_logger(name: str) -> logging.Logger:
    """Get a logger configured for AgentRails.

    Args:
        name: Logger name (typically __name__ of the calling module)

    Returns:
        Configured logger instance

    Configuration:
        AGENTRAILS_LOG_LEVEL: Log level (default: INFO)
        AGENTRAILS_LOG_FORMAT: Format "json" or "text" (default: json)
    """
    logger = logging.getLogger(name)

    # Only configure if no handlers exist (prevents duplicate handlers)
    if not logger.handlers:
        level = os.environ.get("AGENTRAILS_LOG_LEVEL", "INFO").upper()
        log_format = os.environ.get("AGENTRAILS_LOG_FORMAT", "json").lower()

        logger.setLevel(getattr(logging, level, logging.INFO))

        if log_format == "text":
            formatter = TextFormatter("%(asctime)s %(levelname)s %(module)s %(message)s")
        else:
            formatter = JsonFormatter()

        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
