from __future__ import annotations

import datetime
import json
import os
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from tarav.l0._core.clock import iso_z
from tarav.l0._core.errors import CliError
from tarav.l0._core.home import tarav_home_dir


USAGE_RECORD_CLASS = "tarav.agent.usage-record"
# Records written before the Agentos rename stay readable; the registry is never rewritten.
# tarav.breadcrumb 39a8b7f942c5
_READABLE_USAGE_RECORD_CLASSES = frozenset({USAGE_RECORD_CLASS, "agentos.agent.usage-record"})
USAGE_RECORD_SCHEMA_VERSION = 1


def append_usage_record(
    *,
    provider: str,
    account: str,
    home: Path,
    source: str,
    payload: Mapping[str, Any],
) -> Path:
    _validate_required_text(provider, field_name="provider")
    _validate_required_text(account, field_name="account")
    _validate_required_text(source, field_name="source")

    recorded_at = datetime.datetime.now(tz=datetime.UTC)
    registry_dir = tarav_home_dir() / "agent" / "usage-registry"
    record_path = registry_dir / f"{recorded_at:%Y%m}-usage.jsonl"
    record = {
        "schema_version": USAGE_RECORD_SCHEMA_VERSION,
        "class": USAGE_RECORD_CLASS,
        "recorded_at": iso_z(recorded_at, drop_micros=False),
        "provider": provider,
        "account": account,
        "home": str(home.expanduser().resolve()),
        "source": source,
        "payload": dict(payload),
    }
    try:
        line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
    except TypeError as exc:
        raise CliError(f"usage record payload is not JSON serializable: {exc}") from exc
    registry_dir.mkdir(parents=True, exist_ok=True)
    with record_path.open("a", encoding="utf-8") as handle:
        handle.write(line)
    return record_path


def latest_usage_record(
    *,
    provider: str,
    account: str,
    home: Path,
    source: str,
) -> Mapping[str, Any] | None:
    _validate_required_text(provider, field_name="provider")
    _validate_required_text(account, field_name="account")
    _validate_required_text(source, field_name="source")

    registry_dir = tarav_home_dir() / "agent" / "usage-registry"
    if not registry_dir.is_dir():
        return None
    resolved_home = str(home.expanduser().resolve())
    return _latest_matching_record(
        provider=provider,
        account=account,
        source=source,
        home=resolved_home,
    )


def latest_account_usage_record(
    *,
    provider: str,
    account: str,
    source: str,
) -> Mapping[str, Any] | None:
    """Return the latest account-scoped observation regardless of observing home."""

    _validate_required_text(provider, field_name="provider")
    _validate_required_text(account, field_name="account")
    _validate_required_text(source, field_name="source")
    return _latest_matching_record(
        provider=provider,
        account=account,
        source=source,
        home=None,
    )



def iter_usage_records_since(
    cutoff: datetime.datetime,
) -> Iterator[Mapping[str, Any]]:
    """Yield usage records recorded at or after cutoff, newest first.

    Registry files are append-ordered, so reading them newest-first and
    stopping at the first older record bounds the scan to the requested
    window instead of the whole registry.
    """
    registry_dir = tarav_home_dir() / "agent" / "usage-registry"
    if not registry_dir.is_dir():
        return
    boundary = iso_z(cutoff)
    for record_path in sorted(registry_dir.glob("*-usage.jsonl"), reverse=True):
        if not record_path.is_file():
            continue
        for raw_line in _iter_lines_reverse(record_path):
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            recorded_at = record.get("recorded_at")
            if not isinstance(recorded_at, str):
                continue
            if recorded_at < boundary:
                return
            yield record


def _latest_matching_record(
    *,
    provider: str,
    account: str,
    source: str,
    home: str | None,
) -> Mapping[str, Any] | None:
    registry_dir = tarav_home_dir() / "agent" / "usage-registry"
    if not registry_dir.is_dir():
        return None
    for record_path in sorted(registry_dir.glob("*-usage.jsonl"), reverse=True):
        if not record_path.is_file():
            continue
        for raw_line in _iter_lines_reverse(record_path):
            try:
                record = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            if not _record_matches(
                record,
                provider=provider,
                account=account,
                home=home,
                source=source,
            ):
                continue
            payload = record.get("payload")
            if not isinstance(payload, dict):
                continue
            return record
    return None


def _iter_lines_reverse(path: Path, *, chunk_size: int = 8192) -> Iterator[str]:
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        position = handle.tell()
        buffer = b""
        while position > 0:
            read_size = min(chunk_size, position)
            position -= read_size
            handle.seek(position)
            data = handle.read(read_size)
            parts = (data + buffer).split(b"\n")
            buffer = parts[0]
            for line in reversed(parts[1:]):
                if line:
                    yield line.decode("utf-8")
        if buffer:
            yield buffer.decode("utf-8")


def _record_matches(
    record: Mapping[str, Any],
    *,
    provider: str,
    account: str,
    home: str | None,
    source: str,
) -> bool:
    return (
        record.get("schema_version") == USAGE_RECORD_SCHEMA_VERSION
        and record.get("class") in _READABLE_USAGE_RECORD_CLASSES
        and record.get("provider") == provider
        and record.get("account") == account
        and (home is None or record.get("home") == home)
        and record.get("source") == source
        and isinstance(record.get("recorded_at"), str)
    )


def _validate_required_text(value: str, *, field_name: str) -> None:
    if not value:
        raise CliError(f"usage record {field_name} is required")


__all__ = [
    "append_usage_record",
    "iter_usage_records_since",
    "latest_account_usage_record",
    "latest_usage_record",
]
