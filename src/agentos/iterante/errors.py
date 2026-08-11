"""Iterante v1 public controlled-error surface."""

from ._shared.errors import (
    BYPASS_ENV,
    ERROR_LOG_NAME,
    FATAL_MESSAGE,
    dev_bypass,
    record_fatal,
)

__all__ = [
    "BYPASS_ENV",
    "ERROR_LOG_NAME",
    "FATAL_MESSAGE",
    "dev_bypass",
    "record_fatal",
]
