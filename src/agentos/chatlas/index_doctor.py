from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from agentos.chatlas.delta_scan import RAW_PARTITION_MANIFEST_FILENAME
from agentos.chatlas.index_store import load_chatlas_session_index_rows

_REQUIRED_ROW_FIELDS = (
    "uri",
    "provider",
    "session_id",
    "updated_at",
    "home",
    "instance",
    "provider_instance_fingerprint",
    "primary_backing_artifact",
    "backing_artifacts",
    "extractable",
)
_SAMPLE_LIMIT = 10


def run_chatlas_index_doctor(*, chatlas_root: Path | None = None) -> dict[str, object]:
    index = load_chatlas_session_index_rows(chatlas_root=chatlas_root)
    raw_root = index.chatlas_root / "raw"
    checks = [
        _check_required_fields(index.rows),
        _check_duplicate_uri(index.rows),
        _check_duplicate_identity_key(index.rows),
        _check_backing_artifacts_exist(index.rows),
        _check_home_not_managed_storage(index.rows, chatlas_root=index.chatlas_root),
        _check_raw_partition_manifests(index.rows, raw_root=raw_root),
    ]
    error_count = sum(_check_count(check, "error_count") for check in checks)
    warning_count = sum(_check_count(check, "warning_count") for check in checks)
    return {
        "status": "error" if error_count else "ok",
        "command": "chatlas index doctor",
        "chatlas_root": str(index.chatlas_root),
        "session_index_root": str(index.session_index_root),
        "raw_root": str(raw_root),
        "summary": {
            "row_count": len(index.rows),
            "check_count": len(checks),
            "error_count": error_count,
            "warning_count": warning_count,
        },
        "checks": checks,
    }


def format_chatlas_index_doctor_markdown(payload: dict[str, object]) -> str:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    status = payload.get("status", "unknown")
    lines = [
        "Chatlas index doctor",
        "",
        f"Status: {status}",
        f"Rows: {summary.get('row_count', 0)}",
        f"Errors: {summary.get('error_count', 0)}",
    ]
    checks = payload.get("checks")
    if isinstance(checks, list):
        failed = [check for check in checks if isinstance(check, dict) and check.get("status") != "ok"]
        if failed:
            lines.extend(["", "Failed checks:"])
            for check in failed:
                lines.append(
                    f"- {check.get('name', '<unknown>')}: "
                    f"{check.get('error_count', 0)} errors, "
                    f"{check.get('sample_count', 0)} samples"
                )
    return "\n".join(lines)


def _check_required_fields(rows: list[dict[str, Any]]) -> dict[str, object]:
    samples: list[dict[str, object]] = []
    error_count = 0
    for row in rows:
        for field_name in _REQUIRED_ROW_FIELDS:
            if field_name in row and row[field_name] is not None:
                continue
            error_count += 1
            _append_sample(
                samples,
                {
                    **_row_context(row),
                    "field": field_name,
                    "reason": "missing" if field_name not in row else "null",
                },
            )
    return _check_payload("required_fields", error_count=error_count, samples=samples)


def _check_duplicate_uri(rows: list[dict[str, Any]]) -> dict[str, object]:
    values = [_string_or_none(row.get("uri")) for row in rows]
    counts = Counter(value for value in values if value is not None)
    duplicate_values = {value for value, count in counts.items() if count > 1}
    samples = [
        {"uri": value, "count": counts[value]}
        for value in sorted(duplicate_values)[:_SAMPLE_LIMIT]
    ]
    error_count = sum(counts[value] - 1 for value in duplicate_values)
    return _check_payload("duplicate_uri", error_count=error_count, samples=samples)


def _check_duplicate_identity_key(rows: list[dict[str, Any]]) -> dict[str, object]:
    keys = [
        (
            _string_or_none(row.get("provider")),
            _string_or_none(row.get("provider_instance_fingerprint")),
            _string_or_none(row.get("session_id")),
        )
        for row in rows
    ]
    counts = Counter(key for key in keys if all(part is not None for part in key))
    duplicate_keys = {key for key, count in counts.items() if count > 1}
    samples = [
        {
            "provider": provider,
            "provider_instance_fingerprint": fingerprint,
            "session_id": session_id,
            "count": counts[key],
        }
        for key in sorted(duplicate_keys)
        for provider, fingerprint, session_id in [key]
    ][:_SAMPLE_LIMIT]
    error_count = sum(counts[key] - 1 for key in duplicate_keys)
    return _check_payload("duplicate_provider_fingerprint_session", error_count=error_count, samples=samples)


def _check_backing_artifacts_exist(rows: list[dict[str, Any]]) -> dict[str, object]:
    samples: list[dict[str, object]] = []
    error_count = 0
    for row in rows:
        artifacts = _row_backing_artifacts(row)
        for artifact_role, artifact in artifacts:
            path = artifact.get("path") if isinstance(artifact, dict) else None
            if isinstance(path, str) and Path(path).is_file():
                continue
            error_count += 1
            _append_sample(
                samples,
                {
                    **_row_context(row),
                    "artifact": artifact_role,
                    "path": path,
                },
            )
    return _check_payload("backing_artifacts_exist", error_count=error_count, samples=samples)


def _check_home_not_managed_storage(rows: list[dict[str, Any]], *, chatlas_root: Path) -> dict[str, object]:
    managed_roots = [
        chatlas_root / "raw",
        chatlas_root / "index",
        chatlas_root / "views",
        chatlas_root / "archive",
    ]
    samples: list[dict[str, object]] = []
    error_count = 0
    for row in rows:
        home = _string_or_none(row.get("home"))
        if home is None:
            continue
        home_path = Path(home).expanduser()
        for managed_root in managed_roots:
            if _is_relative_to(home_path, managed_root):
                error_count += 1
                _append_sample(
                    samples,
                    {
                        **_row_context(row),
                        "home": home,
                        "managed_root": str(managed_root),
                    },
                )
                break
    return _check_payload("home_not_managed_storage", error_count=error_count, samples=samples)


def _check_raw_partition_manifests(rows: list[dict[str, Any]], *, raw_root: Path) -> dict[str, object]:
    partitions = {
        (_string_or_none(row.get("provider")), _string_or_none(row.get("provider_instance_fingerprint")))
        for row in rows
    }
    samples: list[dict[str, object]] = []
    error_count = 0
    for provider, fingerprint in sorted(partition for partition in partitions if all(partition)):
        manifest_path = raw_root / provider / fingerprint / RAW_PARTITION_MANIFEST_FILENAME
        if manifest_path.is_file():
            continue
        error_count += 1
        _append_sample(
            samples,
            {
                "provider": provider,
                "provider_instance_fingerprint": fingerprint,
                "path": str(manifest_path),
            },
        )
    return _check_payload("raw_partition_manifests", error_count=error_count, samples=samples)


def _row_backing_artifacts(row: dict[str, Any]) -> list[tuple[str, object]]:
    artifacts: list[tuple[str, object]] = [("primary_backing_artifact", row.get("primary_backing_artifact"))]
    backing_artifacts = row.get("backing_artifacts")
    if isinstance(backing_artifacts, list):
        artifacts.extend((f"backing_artifacts[{index}]", artifact) for index, artifact in enumerate(backing_artifacts))
    elif "backing_artifacts" in row:
        artifacts.append(("backing_artifacts", backing_artifacts))
    return artifacts


def _check_payload(name: str, *, error_count: int, samples: list[dict[str, object]]) -> dict[str, object]:
    return {
        "name": name,
        "status": "error" if error_count else "ok",
        "error_count": error_count,
        "warning_count": 0,
        "sample_count": len(samples),
        "samples": samples,
    }


def _row_context(row: dict[str, Any]) -> dict[str, object]:
    context: dict[str, object] = {}
    for field_name in ("uri", "provider", "provider_instance_fingerprint", "session_id"):
        value = row.get(field_name)
        if isinstance(value, str) and value:
            context[field_name] = value
    return context


def _append_sample(samples: list[dict[str, object]], sample: dict[str, object]) -> None:
    if len(samples) < _SAMPLE_LIMIT:
        samples.append(sample)


def _check_count(check: dict[str, object], key: str) -> int:
    value = check.get(key)
    return value if isinstance(value, int) else 0


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


__all__ = ["format_chatlas_index_doctor_markdown", "run_chatlas_index_doctor"]
