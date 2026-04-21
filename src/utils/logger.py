"""Rich logging configuration."""

from __future__ import annotations

import logging
import re

from rich.logging import RichHandler


_SECRET_PATTERNS = [
    re.compile(r"(sk-[A-Za-z0-9_-]+)"),
]


class SecretMaskingFilter(logging.Filter):
    """Redact recognizable secrets from log messages."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Mask secret-like substrings before the record is emitted."""
        if isinstance(record.msg, str):
            record.msg = _mask_secrets(record.msg)
        if record.args:
            if isinstance(record.args, tuple):
                record.args = tuple(_mask_arg(arg) for arg in record.args)
            elif isinstance(record.args, dict):
                record.args = {key: _mask_arg(value) for key, value in record.args.items()}
        return True


def setup_logging(level: str = "INFO", verbose: bool = False) -> None:
    """Configure the root logger with a Rich handler."""
    resolved_level = logging.DEBUG if verbose else getattr(logging, level.upper(), logging.INFO)
    handler = RichHandler(rich_tracebacks=True, show_path=verbose, markup=False)
    handler.addFilter(SecretMaskingFilter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(resolved_level)
    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger instance."""
    return logging.getLogger(name)


def _mask_secrets(value: str) -> str:
    """Apply the configured redaction rules to a string."""
    masked = value
    for pattern in _SECRET_PATTERNS:
        masked = pattern.sub("[REDACTED]", masked)
    return masked


def _mask_arg(value: object) -> object:
    """Mask string-like log args while preserving non-string types."""
    if isinstance(value, str):
        return _mask_secrets(value)
    return value
