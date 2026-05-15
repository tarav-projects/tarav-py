from __future__ import annotations

import datetime
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from agentos._core.errors import CliError
from agentos._core.project import agentos_home_dir


USAGE_RECORD_CLASS = "agentos.agent.usage-record"
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
    registry_dir = agentos_home_dir() / "agent" / "usage-registry"
    record_path = registry_dir / f"{recorded_at:%Y%m}-usage.jsonl"
    record = {
        "schema_version": USAGE_RECORD_SCHEMA_VERSION,
        "class": USAGE_RECORD_CLASS,
        "recorded_at": _iso_z(recorded_at),
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

    registry_dir = agentos_home_dir() / "agent" / "usage-registry"
    if not registry_dir.is_dir():
        return None
    resolved_home = str(home.expanduser().resolve())
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
                home=resolved_home,
                source=source,
            ):
                continue
            payload = record.get("payload")
            if not isinstance(payload, dict):
                continue
            return record
    return None


def _iter_lines_reverse(path: Path, *, chunk_size: int = 8192):
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
    home: str,
    source: str,
) -> bool:
    return (
        record.get("schema_version") == USAGE_RECORD_SCHEMA_VERSION
        and record.get("class") == USAGE_RECORD_CLASS
        and record.get("provider") == provider
        and record.get("account") == account
        and record.get("home") == home
        and record.get("source") == source
        and isinstance(record.get("recorded_at"), str)
    )


def _validate_required_text(value: str, *, field_name: str) -> None:
    if not value:
        raise CliError(f"usage record {field_name} is required")


def _iso_z(value: datetime.datetime) -> str:
    return value.astimezone(datetime.UTC).isoformat().replace("+00:00", "Z")


__all__ = ["append_usage_record", "latest_usage_record"]
