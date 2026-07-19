from __future__ import annotations

import datetime
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentos._core.clock import iso_z
from agentos._core.errors import CliError
from agentos._core.project import agentos_home_dir


HOOK_CONTEXT_SAMPLE_CLASS = "agentos.agent.usage-report-hook-context-sample"
HOOK_CONTEXT_SAMPLE_SCHEMA_VERSION = 1
DEFAULT_HOOK_CONTEXT_SAMPLE_MAX_RECORDS = 50


@dataclass(frozen=True)
class UsageReportResult:
    status: str
    provider: str
    home: Path
    account: str | None
    source: str
    sample_path: Path | None = None

    def summary(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "provider": self.provider,
            "account": self.account,
            "home": str(self.home.expanduser().resolve()),
            "source": self.source,
        }
        if self.sample_path is not None:
            payload["sample"] = {
                "status": "sampled",
                "path": str(self.sample_path),
            }
        return payload


def hook_context_sample_log_dir() -> Path:
    return agentos_home_dir() / "agent" / "usage-report-hook-samples"


def report_usage_from_hook_context(
    *,
    provider: str,
    home: Path,
    raw_context: Mapping[str, Any],
    account: str | None = None,
    source: str | None = None,
    sample_raw_context: bool = False,
    sample_max_records: int = DEFAULT_HOOK_CONTEXT_SAMPLE_MAX_RECORDS,
) -> UsageReportResult:
    _validate_required_text(provider, field_name="provider")
    resolved_source = source or _default_hook_context_source(provider)
    sample_path = (
        append_hook_context_sample(
            provider=provider,
            home=home,
            account=account,
            raw_context=raw_context,
            max_records=sample_max_records,
        )
        if sample_raw_context
        else None
    )
    return UsageReportResult(
        status="no_usage",
        provider=provider,
        home=home,
        account=account,
        source=resolved_source,
        sample_path=sample_path,
    )


def append_hook_context_sample(
    *,
    provider: str,
    home: Path,
    raw_context: Mapping[str, Any],
    account: str | None = None,
    max_records: int = DEFAULT_HOOK_CONTEXT_SAMPLE_MAX_RECORDS,
) -> Path:
    _validate_required_text(provider, field_name="provider")
    if not isinstance(raw_context, Mapping):
        raise CliError("hook context sample raw_context must be a JSON object")
    if max_records <= 0:
        raise CliError("hook context sample max_records must be positive")

    recorded_at = datetime.datetime.now(tz=datetime.UTC)
    record_path = hook_context_sample_log_dir() / f"{recorded_at:%Y%m%d}.jsonl"
    resolved_home = str(home.expanduser().resolve())
    record = {
        "schema_version": HOOK_CONTEXT_SAMPLE_SCHEMA_VERSION,
        "class": HOOK_CONTEXT_SAMPLE_CLASS,
        "recorded_at": iso_z(recorded_at),
        "provider": provider,
        "account": account,
        "home": resolved_home,
        "status": "sampled",
        "raw_context": dict(raw_context),
    }
    try:
        line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
    except TypeError as exc:
        raise CliError(f"hook context sample is not JSON serializable: {exc}") from exc

    record_path.parent.mkdir(parents=True, exist_ok=True)
    with record_path.open("a", encoding="utf-8") as handle:
        handle.write(line)
    os.chmod(record_path, 0o600)
    _trim_hook_context_samples(
        record_path,
        provider=provider,
        account=account,
        home=resolved_home,
        max_records=max_records,
    )
    return record_path


def _trim_hook_context_samples(
    path: Path,
    *,
    provider: str,
    account: str | None,
    home: str,
    max_records: int,
) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    matching_indexes: list[int] = []
    for index, line in enumerate(lines):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        if _sample_matches(record, provider=provider, account=account, home=home):
            matching_indexes.append(index)
    excess = len(matching_indexes) - max_records
    if excess <= 0:
        return
    remove_indexes = set(matching_indexes[:excess])
    kept_lines = [
        line for index, line in enumerate(lines) if index not in remove_indexes
    ]
    path.write_text(
        "".join(f"{line}\n" for line in kept_lines),
        encoding="utf-8",
    )
    os.chmod(path, 0o600)


def _sample_matches(
    record: Mapping[str, Any],
    *,
    provider: str,
    account: str | None,
    home: str,
) -> bool:
    return (
        record.get("schema_version") == HOOK_CONTEXT_SAMPLE_SCHEMA_VERSION
        and record.get("class") == HOOK_CONTEXT_SAMPLE_CLASS
        and record.get("provider") == provider
        and record.get("account") == account
        and record.get("home") == home
    )


def _validate_required_text(value: str, *, field_name: str) -> None:
    if not value:
        raise CliError(f"hook context sample {field_name} is required")


def _default_hook_context_source(provider: str) -> str:
    return f"{provider.replace('-', '_')}_hook_context"


__all__ = [
    "DEFAULT_HOOK_CONTEXT_SAMPLE_MAX_RECORDS",
    "HOOK_CONTEXT_SAMPLE_CLASS",
    "HOOK_CONTEXT_SAMPLE_SCHEMA_VERSION",
    "UsageReportResult",
    "append_hook_context_sample",
    "hook_context_sample_log_dir",
    "report_usage_from_hook_context",
]
