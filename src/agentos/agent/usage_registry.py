from __future__ import annotations

import datetime
import json
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


def _validate_required_text(value: str, *, field_name: str) -> None:
    if not value:
        raise CliError(f"usage record {field_name} is required")


def _iso_z(value: datetime.datetime) -> str:
    return value.astimezone(datetime.UTC).isoformat().replace("+00:00", "Z")


__all__ = ["append_usage_record"]
