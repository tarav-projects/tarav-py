#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import filecmp
import hashlib
import json
import os
import sys
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


USAGE_RECORD_CLASS = "agentos.agent.usage-record"
USAGE_RECORD_SCHEMA_VERSION = 1
ARCHIVE_ROOT = Path.home() / ".tarav" / "archive"
ACTIVE_REGISTRY_DIR = Path.home() / ".tarav" / "agent" / "usage-registry"

LEGACY_ARCHIVES = (
    ARCHIVE_ROOT / "20260516T011731Z" / "raw",
    ARCHIVE_ROOT / "20260516T012119Z" / "raw" / "archive" / "20260515T183834Z" / "raw",
)
BASELINE_REGISTRY_DIR = (
    ARCHIVE_ROOT / "20260516T022536Z" / "raw" / "agent-usage-registry"
)

ACCOUNT_MAP = {
    ("codex", "codex-jp"): ("codex", "jp", "~/.tarav/agent/homes/codex/jp"),
    ("codex", "codex-mm"): ("codex", "mm", "~/.tarav/agent/homes/codex/mm"),
    ("codex", "codex-tk"): ("codex", "tk", "~/.tarav/agent/homes/codex/tk"),
    ("codex", "codex-br"): ("codex", "br", "~/.tarav/agent/homes/codex/br"),
    ("claude-code", "claude-main"): (
        "claude-code",
        "browser-jp",
        "~/.tarav/agent/homes/claude-code/browser-jp",
    ),
}

SKIP_ACCOUNTS = {
    ("codex", "codex-main"): "ambiguous legacy singleton conflicts with codex-jp snapshots",
    ("copilot", "copilot-main"): "no current registered Copilot account",
    ("copilot-cli", "copilot-main"): "no current registered Copilot account",
}

REQUIRED_RECORD_FIELDS = {
    "schema_version",
    "class",
    "recorded_at",
    "provider",
    "account",
    "home",
    "source",
    "payload",
}


class MigrationError(Exception):
    pass


@dataclass(frozen=True)
class EntryContext:
    path: Path
    line_number: int
    snapshot_recorded_at: str | None
    provider: str | None = None
    legacy_account: str | None = None
    usage_status: str | None = None
    usage_source: str | None = None
    entry: dict[str, Any] | None = None


class EntryError(MigrationError):
    def __init__(self, message: str, context: EntryContext) -> None:
        super().__init__(message)
        self.context = context


@dataclass
class MigrationResult:
    records_by_month: dict[str, list[dict[str, Any]]]
    report: Counter[str]
    skipped_accounts: Counter[str]
    per_account: Counter[str]
    monthly_counts: Counter[str]
    exact_duplicates: int
    staged_dir: Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate archived account usage observations into staged usage-registry files."
    )
    parser.add_argument("--dry-run", action="store_true", help="validate and stage without writing")
    parser.add_argument("--write", action="store_true", help="replace active registry files after validation")
    parser.add_argument("--limit", type=int, default=None, help="stop after reading N legacy snapshot lines")
    parser.add_argument(
        "--show-entry-on-error",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="print compact offending entry JSON when conversion fails",
    )
    args = parser.parse_args()

    if args.write and args.dry_run:
        print("error: choose either --dry-run or --write", file=sys.stderr)
        return 2
    if not args.write:
        args.dry_run = True

    try:
        result = run_migration(limit=args.limit)
        if args.write:
            write_active_registry(result.records_by_month)
            print_report(result, mode="write")
        else:
            print_report(result, mode="dry-run")
        return 0
    except EntryError as exc:
        print_entry_error(exc, show_entry=args.show_entry_on_error)
        return 1
    except MigrationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def run_migration(*, limit: int | None = None) -> MigrationResult:
    validate_sources()
    report: Counter[str] = Counter()
    skipped_accounts: Counter[str] = Counter()
    per_account: Counter[str] = Counter()

    baseline_rows = load_baseline_registry(report=report)
    converted_rows = convert_legacy_archives(
        report=report,
        skipped_accounts=skipped_accounts,
        per_account=per_account,
        limit=limit,
    )
    rows, exact_duplicates = dedupe_records([*baseline_rows, *converted_rows])
    records_by_month = group_records_by_month(rows)
    staged_dir = stage_records(records_by_month)
    validate_staged_registry(staged_dir)
    monthly_counts = Counter({month: len(records) for month, records in records_by_month.items()})
    return MigrationResult(
        records_by_month=records_by_month,
        report=report,
        skipped_accounts=skipped_accounts,
        per_account=per_account,
        monthly_counts=monthly_counts,
        exact_duplicates=exact_duplicates,
        staged_dir=staged_dir,
    )


def validate_sources() -> None:
    for path in (*LEGACY_ARCHIVES, BASELINE_REGISTRY_DIR):
        if not path.exists():
            raise MigrationError(f"missing source archive: {path}")
        if not path.is_dir():
            raise MigrationError(f"source archive is not a directory: {path}")
        if not path.is_relative_to(ARCHIVE_ROOT):
            raise MigrationError(f"source archive is outside archive root: {path}")


def load_baseline_registry(*, report: Counter[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(BASELINE_REGISTRY_DIR.glob("*-usage.jsonl")):
        report["baseline_files"] += 1
        for line_number, item in iter_jsonl(path):
            context = EntryContext(path=path, line_number=line_number, snapshot_recorded_at=None)
            validate_usage_record(item, context=context)
            rows.append(item)
            report["baseline_rows"] += 1
    return rows


def convert_legacy_archives(
    *,
    report: Counter[str],
    skipped_accounts: Counter[str],
    per_account: Counter[str],
    limit: int | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    read_lines = 0
    for root in LEGACY_ARCHIVES:
        report["legacy_archives"] += 1
        for path in sorted((root / "history" / "segments").glob("*.jsonl")):
            report["legacy_files"] += 1
            for line_number, snapshot in iter_jsonl(path):
                read_lines += 1
                report["legacy_snapshot_lines"] += 1
                if limit is not None and read_lines > limit:
                    return rows
                context = EntryContext(
                    path=path,
                    line_number=line_number,
                    snapshot_recorded_at=snapshot.get("recorded_at")
                    if isinstance(snapshot, dict)
                    else None,
                    entry=snapshot if isinstance(snapshot, dict) else None,
                )
                if not isinstance(snapshot, dict):
                    raise EntryError("legacy snapshot is not an object", context)
                rows.extend(convert_snapshot(snapshot, context, report, skipped_accounts, per_account))
    return rows


def convert_snapshot(
    snapshot: dict[str, Any],
    context: EntryContext,
    report: Counter[str],
    skipped_accounts: Counter[str],
    per_account: Counter[str],
) -> list[dict[str, Any]]:
    recorded_at = snapshot.get("recorded_at")
    if not isinstance(recorded_at, str):
        raise EntryError("legacy snapshot recorded_at is missing or not text", context)
    parse_time(recorded_at, context=context)
    providers = snapshot.get("providers")
    if not isinstance(providers, list):
        raise EntryError("legacy snapshot providers is missing or not a list", context)

    rows: list[dict[str, Any]] = []
    for provider_block in providers:
        if not isinstance(provider_block, dict):
            raise EntryError("legacy provider block is not an object", context)
        accounts = provider_block.get("accounts")
        if not isinstance(accounts, list):
            raise EntryError("legacy provider accounts is missing or not a list", context)
        for account_entry in accounts:
            if not isinstance(account_entry, dict):
                raise EntryError("legacy account entry is not an object", context)
            account_context = context_for_account(context, account_entry)
            usage_status = account_entry.get("usage_status")
            if usage_status != "ok":
                report["skipped_non_ok"] += 1
                continue
            report["successful_observations"] += 1
            provider = text_field(account_entry, "provider", account_context)
            legacy_id = text_field(account_entry, "id", account_context)
            skip_reason = SKIP_ACCOUNTS.get((provider, legacy_id))
            if skip_reason:
                skipped_accounts[f"{provider}/{legacy_id}: {skip_reason}"] += 1
                continue
            mapped = ACCOUNT_MAP.get((provider, legacy_id))
            if mapped is None:
                raise EntryError("successful usage observation has no account mapping", account_context)
            target_provider, target_account, target_home = mapped
            converted_payload = convert_payload(account_entry, account_context)
            if converted_payload is None:
                report["skipped_incomplete_usage"] += 1
                continue
            source, payload = converted_payload
            record = make_usage_record(
                recorded_at=recorded_at,
                provider=target_provider,
                account=target_account,
                home=Path(target_home),
                source=source,
                payload=payload,
            )
            validate_usage_record(record, context=account_context)
            rows.append(record)
            report["generated_rows"] += 1
            per_account[f"{target_provider}/{target_account}/{source}"] += 1
    return rows


def context_for_account(context: EntryContext, entry: dict[str, Any]) -> EntryContext:
    provider = entry.get("provider") if isinstance(entry.get("provider"), str) else None
    legacy_account = entry.get("id") if isinstance(entry.get("id"), str) else None
    usage_status = entry.get("usage_status") if isinstance(entry.get("usage_status"), str) else None
    usage_source = entry.get("usage_source") if isinstance(entry.get("usage_source"), str) else None
    return EntryContext(
        path=context.path,
        line_number=context.line_number,
        snapshot_recorded_at=context.snapshot_recorded_at,
        provider=provider,
        legacy_account=legacy_account,
        usage_status=usage_status,
        usage_source=usage_source,
        entry=entry,
    )


def convert_payload(entry: dict[str, Any], context: EntryContext) -> tuple[str, dict[str, Any]] | None:
    provider = text_field(entry, "provider", context)
    usage_source = text_field(entry, "usage_source", context)
    if provider == "codex":
        if usage_source != "app-server":
            raise EntryError(f"unsupported Codex usage_source: {usage_source}", context)
        payload = nested_dict(entry, context, "provider_status", "rate_limits")
        require_keys(payload, {"rateLimits", "rateLimitsByLimitId"}, context)
        return "app_server", payload
    if provider == "claude-code":
        if usage_source not in {"interactive-statusline", "live-refresh"}:
            raise EntryError(f"unsupported Claude usage_source: {usage_source}", context)
        payload = convert_claude_payload(entry, context)
        if payload is None:
            return None
        return "statusline_rate_limits", payload
    raise EntryError(f"unsupported provider: {provider}", context)


def convert_claude_payload(entry: dict[str, Any], context: EntryContext) -> dict[str, Any] | None:
    statusline_rate_limits = get_nested_dict(
        entry,
        "provider_status",
        "live_usage_refresh",
        "statusline",
        "rate_limits",
    )
    if statusline_rate_limits is not None:
        return convert_claude_statusline_payload(statusline_rate_limits, context)
    usage_limits = get_nested_value(entry, "usage", "limits")
    if isinstance(usage_limits, list):
        return convert_claude_usage_limits_payload(usage_limits, context)
    raise EntryError("Claude usage row has no statusline rate_limits or usage.limits", context)


def convert_claude_statusline_payload(rate_limits: dict[str, Any], context: EntryContext) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for old_name, new_name in (("five_hour", "five_hour"), ("seven_day", "seven_day")):
        raw_limit = rate_limits.get(old_name)
        if not isinstance(raw_limit, dict):
            raise EntryError(f"Claude rate limit {old_name} is missing or not an object", context)
        used_percentage = raw_limit.get("used_percentage")
        resets_at = raw_limit.get("resets_at")
        if not isinstance(used_percentage, int | float):
            raise EntryError(f"Claude rate limit {old_name}.used_percentage is invalid", context)
        if not isinstance(resets_at, int | float):
            raise EntryError(f"Claude rate limit {old_name}.resets_at is invalid", context)
        payload[new_name] = {
            "resets_at": iso_from_epoch(resets_at),
            "utilization": float(used_percentage),
        }
    return payload


def convert_claude_usage_limits_payload(usage_limits: list[Any], context: EntryContext) -> dict[str, Any] | None:
    payload: dict[str, Any] = {}
    for raw_limit in usage_limits:
        if not isinstance(raw_limit, dict):
            raise EntryError("Claude usage.limits contains a non-object item", context)
        limit_type = raw_limit.get("limit_type")
        if limit_type not in {"five_hour", "seven_day"}:
            continue
        used_percent = raw_limit.get("used_percent")
        resets_at = raw_limit.get("resets_at") or raw_limit.get("period_ends_at")
        if used_percent is None:
            continue
        if not isinstance(used_percent, int | float):
            raise EntryError(f"Claude usage limit {limit_type}.used_percent is invalid", context)
        if not isinstance(resets_at, str):
            raise EntryError(f"Claude usage limit {limit_type}.resets_at is invalid", context)
        payload[limit_type] = {
            "resets_at": iso_z(parse_time(resets_at, context=context)),
            "utilization": float(used_percent),
        }
    if not payload:
        return None
    return payload


def make_usage_record(
    *,
    recorded_at: str,
    provider: str,
    account: str,
    home: Path,
    source: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": USAGE_RECORD_SCHEMA_VERSION,
        "class": USAGE_RECORD_CLASS,
        "recorded_at": iso_z(parse_time(recorded_at)),
        "provider": provider,
        "account": account,
        "home": str(home.expanduser().resolve()),
        "source": source,
        "payload": payload,
    }


def dedupe_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    by_exact_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    by_observation_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    exact_duplicates = 0
    for record in records:
        exact_key = record_identity(record, include_payload=True)
        observation_key = record_identity(record, include_payload=False)
        existing_observation = by_observation_key.get(observation_key)
        if existing_observation is not None and record_payload_hash(existing_observation) != record_payload_hash(
            record
        ):
            raise MigrationError(
                "conflicting usage records for "
                f"{record['provider']}/{record['account']} {record['source']} {record['recorded_at']}"
            )
        if exact_key in by_exact_key:
            exact_duplicates += 1
            continue
        by_exact_key[exact_key] = record
        by_observation_key[observation_key] = record
    return list(by_exact_key.values()), exact_duplicates


def group_records_by_month(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    records_by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        recorded_at = parse_time(record["recorded_at"])
        month = f"{recorded_at:%Y%m}"
        records_by_month[month].append(record)
    for rows in records_by_month.values():
        rows.sort(key=sort_key)
    return dict(sorted(records_by_month.items()))


def stage_records(records_by_month: dict[str, list[dict[str, Any]]]) -> Path:
    staging_parent = Path(tempfile.mkdtemp(prefix="usage-registry-migration-"))
    for month, records in records_by_month.items():
        path = staging_parent / f"{month}-usage.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    return staging_parent


def validate_staged_registry(staged_dir: Path) -> None:
    for path in sorted(staged_dir.glob("*-usage.jsonl")):
        previous_time: dt.datetime | None = None
        for line_number, record in iter_jsonl(path):
            context = EntryContext(path=path, line_number=line_number, snapshot_recorded_at=None)
            validate_usage_record(record, context=context)
            recorded_at = parse_time(record["recorded_at"], context=context)
            if previous_time is not None and recorded_at < previous_time:
                raise EntryError("staged monthly file is not sorted by recorded_at", context)
            previous_time = recorded_at


def write_active_registry(records_by_month: dict[str, list[dict[str, Any]]]) -> None:
    check_active_target_matches_baseline()
    ACTIVE_REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    staged_dir = stage_records(records_by_month)
    validate_staged_registry(staged_dir)
    for staged_path in sorted(staged_dir.glob("*-usage.jsonl")):
        target_path = ACTIVE_REGISTRY_DIR / staged_path.name
        os.replace(staged_path, target_path)


def check_active_target_matches_baseline() -> None:
    if not ACTIVE_REGISTRY_DIR.exists():
        return
    baseline_files = {path.name: path for path in BASELINE_REGISTRY_DIR.glob("*-usage.jsonl")}
    active_files = {path.name: path for path in ACTIVE_REGISTRY_DIR.glob("*-usage.jsonl")}
    for name, active_path in active_files.items():
        baseline_path = baseline_files.get(name)
        if baseline_path is None:
            raise MigrationError(
                f"active registry has {name}, but the archived baseline does not; archive current registry first"
            )
        if not filecmp.cmp(active_path, baseline_path, shallow=False):
            raise MigrationError(
                f"active registry file changed after archived baseline: {active_path}; "
                "archive current registry again before writing"
            )


def validate_usage_record(record: Any, *, context: EntryContext) -> None:
    if not isinstance(record, dict):
        raise EntryError("usage record is not an object", context)
    if set(record) != REQUIRED_RECORD_FIELDS:
        raise EntryError(
            "usage record fields do not match current registry standard: "
            + ", ".join(sorted(set(record) ^ REQUIRED_RECORD_FIELDS)),
            context,
        )
    if record["schema_version"] != USAGE_RECORD_SCHEMA_VERSION:
        raise EntryError("usage record schema_version is invalid", context)
    if record["class"] != USAGE_RECORD_CLASS:
        raise EntryError("usage record class is invalid", context)
    for field_name in ("recorded_at", "provider", "account", "home", "source"):
        if not isinstance(record[field_name], str) or not record[field_name]:
            raise EntryError(f"usage record {field_name} is missing or invalid", context)
    if not isinstance(record["payload"], dict):
        raise EntryError("usage record payload is not an object", context)
    parse_time(record["recorded_at"], context=context)
    json.dumps(record, sort_keys=True, separators=(",", ":"))


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield line_number, json.loads(line)
            except json.JSONDecodeError as exc:
                context = EntryContext(path=path, line_number=line_number, snapshot_recorded_at=None)
                raise EntryError(f"invalid JSON: {exc}", context) from exc


def nested_dict(entry: dict[str, Any], context: EntryContext, *path: str) -> dict[str, Any]:
    value: Any = entry
    for key in path:
        if not isinstance(value, dict):
            raise EntryError(".".join(path) + " is missing", context)
        value = value.get(key)
    if not isinstance(value, dict):
        raise EntryError(".".join(path) + " is missing or not an object", context)
    return value


def get_nested_value(entry: dict[str, Any], *path: str) -> Any:
    value: Any = entry
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def get_nested_dict(entry: dict[str, Any], *path: str) -> dict[str, Any] | None:
    value = get_nested_value(entry, *path)
    return value if isinstance(value, dict) else None


def require_keys(payload: dict[str, Any], keys: set[str], context: EntryContext) -> None:
    missing = sorted(keys - set(payload))
    if missing:
        raise EntryError("payload missing keys: " + ", ".join(missing), context)


def text_field(entry: dict[str, Any], field_name: str, context: EntryContext) -> str:
    value = entry.get(field_name)
    if not isinstance(value, str) or not value:
        raise EntryError(f"legacy account {field_name} is missing or invalid", context)
    return value


def parse_time(value: str, *, context: EntryContext | None = None) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        if context is None:
            raise MigrationError(f"invalid timestamp: {value}") from exc
        raise EntryError(f"invalid timestamp: {value}", context) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC)


def iso_z(value: dt.datetime) -> str:
    return value.astimezone(dt.UTC).isoformat().replace("+00:00", "Z")


def iso_from_epoch(value: int | float) -> str:
    return iso_z(dt.datetime.fromtimestamp(value, tz=dt.UTC))


def record_identity(record: dict[str, Any], *, include_payload: bool) -> tuple[Any, ...]:
    parts: list[Any] = [
        record["provider"],
        record["account"],
        record["home"],
        record["source"],
        record["recorded_at"],
    ]
    if include_payload:
        parts.append(record_payload_hash(record))
    return tuple(parts)


def record_payload_hash(record: dict[str, Any]) -> str:
    raw = json.dumps(record["payload"], sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def sort_key(record: dict[str, Any]) -> tuple[Any, ...]:
    return (
        parse_time(record["recorded_at"]),
        record["provider"],
        record["account"],
        record["source"],
        record_payload_hash(record),
    )


def print_report(result: MigrationResult, *, mode: str) -> None:
    title = "usage-registry migration dry-run ok" if mode == "dry-run" else "usage-registry migration write ok"
    print(title)
    print(f"archives: legacy={result.report['legacy_archives']} baseline=1")
    print(
        "scanned: "
        f"legacy_files={result.report['legacy_files']} "
        f"legacy_snapshots={result.report['legacy_snapshot_lines']} "
        f"baseline_rows={result.report['baseline_rows']}"
    )
    print(
        "converted: "
        f"successful={result.report['successful_observations']} "
        f"generated={result.report['generated_rows']} "
        f"skipped_non_ok={result.report['skipped_non_ok']} "
        f"skipped_incomplete={result.report['skipped_incomplete_usage']} "
        f"exact_duplicates={result.exact_duplicates}"
    )
    if result.skipped_accounts:
        print("skipped_accounts:")
        for label, count in sorted(result.skipped_accounts.items()):
            print(f"  {label}: {count}")
    print("monthly_files:")
    for month, count in sorted(result.monthly_counts.items()):
        print(f"  {month}-usage.jsonl: {count}")
    print("provider_accounts:")
    for label, count in sorted(result.per_account.items()):
        print(f"  {label}: {count}")
    if mode == "dry-run":
        print("active_target: not modified")
    else:
        print(f"active_target: {ACTIVE_REGISTRY_DIR}")


def print_entry_error(exc: EntryError, *, show_entry: bool) -> None:
    context = exc.context
    print(f"error: {exc}", file=sys.stderr)
    print(f"source: {context.path}:{context.line_number}", file=sys.stderr)
    if context.snapshot_recorded_at:
        print(f"snapshot_recorded_at: {context.snapshot_recorded_at}", file=sys.stderr)
    if context.provider or context.legacy_account:
        print(
            "legacy: "
            f"provider={context.provider or '<unknown>'} "
            f"account={context.legacy_account or '<unknown>'} "
            f"usage_status={context.usage_status or '<unknown>'} "
            f"usage_source={context.usage_source or '<unknown>'}",
            file=sys.stderr,
        )
    if show_entry and context.entry is not None:
        print(
            "entry: "
            + json.dumps(context.entry, sort_keys=True, separators=(",", ":"))[:4000],
            file=sys.stderr,
        )


if __name__ == "__main__":
    raise SystemExit(main())
