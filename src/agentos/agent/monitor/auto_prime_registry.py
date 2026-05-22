from __future__ import annotations

import datetime
import json
from collections.abc import Mapping
from pathlib import Path

from agentos._core.project import agentos_home_dir


AUTO_PRIME_EVENT_REGISTRY_RELATIVE_PATH = (
    "agent",
    "monitor",
    "auto-prime-events.jsonl",
)


def auto_prime_event_registry_path() -> Path:
    return agentos_home_dir().joinpath(*AUTO_PRIME_EVENT_REGISTRY_RELATIVE_PATH)


def append_auto_prime_event(
    event_type: str,
    *,
    provider: object,
    account: object,
    home: object,
    limit_id: object = None,
    period_key: object = None,
    trigger_reasons: object = None,
    tick: int | None = None,
    observed_at: object = None,
    scan_at: object = None,
    status: object = None,
    error: Mapping[str, object] | None = None,
    extra: Mapping[str, object] | None = None,
) -> dict[str, object]:
    record: dict[str, object] = {
        "event_type": event_type,
        "timestamp": datetime.datetime.now(tz=datetime.UTC).isoformat(),
        "provider": provider,
        "account": account,
        "home": str(home) if home is not None else None,
        "limit_id": limit_id,
        "period_key": period_key,
        "trigger_reasons": list(trigger_reasons)
        if isinstance(trigger_reasons, tuple | list | set)
        else trigger_reasons,
        "tick": tick,
        "observed_at": observed_at,
        "scan_at": scan_at,
        "status": status,
    }
    if error is not None:
        record["error"] = {
            "type": error.get("type") or error.get("error_type"),
            "message": error.get("message"),
        }
    if extra is not None:
        for key, value in extra.items():
            if key not in record:
                record[key] = value
    compact_record = {key: value for key, value in record.items() if value is not None}
    path = auto_prime_event_registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(compact_record, sort_keys=True))
        stream.write("\n")
    return compact_record

