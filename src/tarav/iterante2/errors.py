# $kw: --from Iterante.Runtime
"""Iterante v2 public controlled-error surface."""

from tarav.iterante._shared.errors import (
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
