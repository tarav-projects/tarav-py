from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any

from tarav._core.clock import iso_z
from tarav._core.project import tarav_home_dir


OPERATIONAL_LOG_CLASS = "tarav.operational-log"
OPERATIONAL_LOG_SCHEMA_VERSION = 1
DEFAULT_RETENTION_DAYS = 30
LOGGER_NAMESPACE = "tarav"
_HANDLER_MARKER = "_tarav_operational_handler"


def operational_log_dir() -> Path:
    return tarav_home_dir() / "logs" / "operational"


def operational_log_path(*, day: date | None = None) -> Path:
    resolved_day = day or datetime.now(timezone.utc).date()
    return operational_log_dir() / f"{resolved_day:%Y%m%d}.jsonl"


def event_extra(event: str, **context: object) -> dict[str, object]:
    """Build the structured fields carried by one operational log record."""
    return {"event": event, "context": context}


def configure_operational_logging(
    *,
    file_level: int = logging.DEBUG,
    console_level: int = logging.WARNING,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> Path:
    """Configure Tarav-owned process logging.

    Libraries only emit records. Tarav entrypoints call this function to persist
    diagnostics and expose warnings without configuring the host application at
    import time. Filesystem failures are deliberately non-fatal.
    """
    if retention_days < 1:
        raise ValueError("retention_days must be at least 1")

    log_dir = operational_log_dir()
    _prepare_log_dir(log_dir)
    _prune_operational_logs(log_dir, retention_days=retention_days)

    logger = logging.getLogger(LOGGER_NAMESPACE)
    logger.setLevel(min(file_level, console_level))
    logger.propagate = False
    _remove_configured_handlers(logger)

    file_handler = _DailyJsonlHandler(
        log_dir=log_dir,
        level=file_level,
        retention_days=retention_days,
    )
    setattr(file_handler, _HANDLER_MARKER, True)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(
        logging.Formatter("[tarav] %(levelname)s %(name)s: %(message)s")
    )
    setattr(console_handler, _HANDLER_MARKER, True)
    logger.addHandler(console_handler)
    return operational_log_path()


class _DailyJsonlHandler(logging.Handler):
    def __init__(self, *, log_dir: Path, level: int, retention_days: int) -> None:
        super().__init__(level=level)
        self.log_dir = log_dir
        self.retention_days = retention_days
        self._last_pruned_day: date | None = None

    def emit(self, record: logging.LogRecord) -> None:
        try:
            now = datetime.now(timezone.utc)
            _prepare_log_dir(self.log_dir)
            if self._last_pruned_day != now.date():
                _prune_operational_logs(
                    self.log_dir,
                    retention_days=self.retention_days,
                )
                self._last_pruned_day = now.date()
            path = self.log_dir / f"{now:%Y%m%d}.jsonl"
            payload: dict[str, object] = {
                "schema_version": OPERATIONAL_LOG_SCHEMA_VERSION,
                "class": OPERATIONAL_LOG_CLASS,
                "recorded_at": iso_z(now, drop_micros=False),
                "level": record.levelname,
                "logger": record.name,
                "event": _record_event(record),
                "pid": record.process,
                "message": record.getMessage(),
                "context": _record_context(record),
            }
            if record.exc_info:
                formatter = self.formatter or logging.Formatter()
                payload["exception"] = formatter.formatException(record.exc_info)
            line = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
            descriptor = os.open(
                path,
                os.O_APPEND | os.O_CREAT | os.O_WRONLY,
                0o600,
            )
            try:
                os.fchmod(descriptor, 0o600)
                os.write(descriptor, (line + "\n").encode("utf-8"))
            finally:
                os.close(descriptor)
        except Exception:
            # Diagnostics must never break the operation they describe.
            return


def _record_event(record: logging.LogRecord) -> str:
    value = getattr(record, "event", "log")
    return value if isinstance(value, str) and value else "log"


def _record_context(record: logging.LogRecord) -> dict[str, Any]:
    value = getattr(record, "context", {})
    if not isinstance(value, Mapping):
        return {"value": value}
    return {str(key): item for key, item in value.items()}


def _prepare_log_dir(log_dir: Path) -> None:
    try:
        home = tarav_home_dir()
        home_existed = home.exists()
        home.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not home_existed:
            home.chmod(0o700)
        logs_dir = home / "logs"
        logs_dir.mkdir(exist_ok=True, mode=0o700)
        logs_dir.chmod(0o700)
        log_dir.mkdir(exist_ok=True, mode=0o700)
        log_dir.chmod(0o700)
    except OSError:
        return


def _prune_operational_logs(log_dir: Path, *, retention_days: int) -> None:
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=retention_days - 1)
    try:
        candidates = tuple(log_dir.glob("????????.jsonl"))
    except OSError:
        return
    for path in candidates:
        try:
            day = datetime.strptime(path.stem, "%Y%m%d").date()
        except ValueError:
            continue
        if day >= cutoff:
            continue
        try:
            path.unlink()
        except OSError:
            continue


def _remove_configured_handlers(logger: logging.Logger) -> None:
    for handler in tuple(logger.handlers):
        if not getattr(handler, _HANDLER_MARKER, False):
            continue
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            continue


__all__ = [
    "DEFAULT_RETENTION_DAYS",
    "OPERATIONAL_LOG_CLASS",
    "OPERATIONAL_LOG_SCHEMA_VERSION",
    "configure_operational_logging",
    "event_extra",
    "operational_log_dir",
    "operational_log_path",
]
