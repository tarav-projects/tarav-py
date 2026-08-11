from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentos._core.errors import CliError
from agentos.chatlas._payload_helpers import string_or_none
from agentos.chatlas.index_writer import archive_versions_for
from agentos.chatlas.index_store import (
    ChatlasSessionIndexCache,
    load_chatlas_session_index_rows,
)
from agentos.chatlas.index_time import chatlas_index_timestamp_sort_value
from agentos.chatlas.index_time import parse_chatlas_index_timestamp

_DEFAULT_LIMIT = 50


def chatlas_index_query(
    *,
    uri: str | None = None,
    identity_hash: str | None = None,
    project: str | Path | None = None,
    project_base: str | None = None,
    providers: tuple[str, ...] | None = None,
    instances: tuple[str, ...] | None = None,
    provider_instance_fingerprint: str | None = None,
    session_id: str | None = None,
    display_name: str | None = None,
    extractable_only: bool = False,
    active_after: str | None = None,
    sort: str = "lexical",
    limit: int | None = None,
    chatlas_root: Path | None = None,
    index_cache: ChatlasSessionIndexCache | None = None,
) -> dict[str, object]:
    index = load_chatlas_session_index_rows(
        chatlas_root=chatlas_root,
        identity_hash=identity_hash,
        providers=providers,
        cache=index_cache,
    )
    filters = {
        "uri": uri,
        "identity_hash": identity_hash,
        "project": _normalized_project_selector_path(project),
        "project_base": project_base,
        "providers": list(providers) if providers is not None else None,
        "instances": list(instances) if instances is not None else None,
        "provider_instance_fingerprint": provider_instance_fingerprint,
        "session_id": session_id,
        "display_name": display_name,
        "extractable": extractable_only,
        "active_after": active_after,
    }
    matched_rows = [
        row
        for row in index.rows
        if chatlas_index_row_matches(
            row,
            uri=uri,
            identity_hash=identity_hash,
            project=project,
            project_base=project_base,
            providers=providers,
            instances=instances,
            provider_instance_fingerprint=provider_instance_fingerprint,
            session_id=session_id,
            display_name=display_name,
            extractable_only=extractable_only,
            active_after=active_after,
        )
    ]
    sorted_rows = sort_chatlas_index_rows(matched_rows, sort=sort)
    effective_limit = _DEFAULT_LIMIT if limit is None else limit
    limited_rows = sorted_rows[:effective_limit]
    index_matched_row_count = len(matched_rows)
    return {
        "status": "ok",
        "command": "chatlas index query",
        "chatlas_root": str(index.chatlas_root),
        "session_index_root": str(index.session_index_root),
        "filters": filters,
        "sort": sort,
        "limit": effective_limit,
        "partition_count": index.partition_count,
        "scanned_row_count": index.scanned_row_count,
        "skipped_row_count": index.skipped_row_count,
        "index_matched_row_count": index_matched_row_count,
        "candidate_row_count": index_matched_row_count,
        "query_matched_row_count": index_matched_row_count,
        "returned_row_count": len(limited_rows),
        "rows": limited_rows,
    }


def select_one_chatlas_index_row(
    *,
    command: str,
    uri: str | None = None,
    identity_hash: str | None = None,
    project: str | Path | None = None,
    project_base: str | None = None,
    providers: tuple[str, ...] | None = None,
    instances: tuple[str, ...] | None = None,
    provider_instance_fingerprint: str | None = None,
    session_id: str | None = None,
    display_name: str | None = None,
    extractable_only: bool = False,
    active_after: str | None = None,
    sort: str = "lexical",
    limit: int | None = None,
    chatlas_root: Path | None = None,
    index_cache: ChatlasSessionIndexCache | None = None,
) -> dict[str, Any]:
    _validate_index_selector(
        command=command,
        uri=uri,
        identity_hash=identity_hash,
        project=project,
        project_base=project_base,
        providers=providers,
        instances=instances,
        provider_instance_fingerprint=provider_instance_fingerprint,
        session_id=session_id,
        display_name=display_name,
        extractable_only=extractable_only,
        active_after=active_after,
    )
    payload = chatlas_index_query(
        uri=uri,
        identity_hash=identity_hash,
        project=project,
        project_base=project_base,
        providers=providers,
        instances=instances,
        provider_instance_fingerprint=provider_instance_fingerprint,
        session_id=session_id,
        display_name=display_name,
        extractable_only=extractable_only,
        active_after=active_after,
        sort=sort,
        limit=limit,
        chatlas_root=chatlas_root,
        index_cache=index_cache,
    )
    index_matched_row_count = payload.get("index_matched_row_count")
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise CliError("Chatlas index query returned an invalid rows payload")
    if index_matched_row_count == 1 and len(rows) == 1 and isinstance(rows[0], dict):
        return rows[0]
    if index_matched_row_count == 0:
        raise CliError(f"no indexed Chatlas session matched the {command} selector")
    raise CliError(
        f"multiple Chatlas sessions matched the {command} selector: "
        f"{_index_candidate_summary(rows)}"
    )


def _validate_index_selector(
    *,
    command: str,
    uri: str | None,
    identity_hash: str | None,
    project: str | Path | None,
    project_base: str | None,
    providers: tuple[str, ...] | None,
    instances: tuple[str, ...] | None,
    provider_instance_fingerprint: str | None,
    session_id: str | None,
    display_name: str | None,
    extractable_only: bool,
    active_after: str | None,
) -> None:
    if any(
        (
            uri,
            identity_hash,
            project,
            project_base,
            providers,
            instances,
            provider_instance_fingerprint,
            session_id,
            display_name,
            extractable_only,
            active_after,
        )
    ):
        return
    raise CliError(f"{command} requires at least one index query selector option")


def _index_candidate_summary(rows: list[object]) -> str:
    candidates: list[str] = []
    for row in rows[:5]:
        if not isinstance(row, dict):
            continue
        identity = string_or_none(row.get("uri")) or string_or_none(
            row.get("session_id")
        )
        if identity is not None:
            candidates.append(identity)
    if not candidates:
        return "<no valid candidates returned>"
    return ", ".join(candidates)


def chatlas_index_row_matches(
    row: dict[str, Any],
    *,
    uri: str | None,
    identity_hash: str | None,
    project: str | Path | None,
    project_base: str | None,
    providers: tuple[str, ...] | None,
    instances: tuple[str, ...] | None,
    provider_instance_fingerprint: str | None,
    session_id: str | None,
    display_name: str | None,
    extractable_only: bool,
    active_after: str | None,
    active_before: str | None = None,
) -> bool:
    if not chatlas_index_row_matches_logical(
        row,
        identity_hash=identity_hash,
        project=project,
        project_base=project_base,
        providers=providers,
        session_id=session_id,
        display_name=display_name,
        extractable_only=extractable_only,
        active_after=active_after,
        active_before=active_before,
    ):
        return False
    if uri is None and instances is None and provider_instance_fingerprint is None:
        return True
    return any(
        _version_matches_selector(
            version,
            uri=uri,
            instances=instances,
            provider_instance_fingerprint=provider_instance_fingerprint,
        )
        for version in archive_versions_for(row)
    )


def chatlas_index_row_matches_logical(
    row: dict[str, Any],
    *,
    identity_hash: str | None,
    project: str | Path | None,
    project_base: str | None,
    providers: tuple[str, ...] | None,
    session_id: str | None,
    display_name: str | None,
    extractable_only: bool,
    active_after: str | None,
    active_before: str | None = None,
) -> bool:
    if identity_hash is not None and not str(row.get("identity_hash") or "").startswith(
        identity_hash
    ):
        return False
    if project is not None and _row_project_path(
        row
    ) != _normalized_project_selector_path(project):
        return False
    if project_base is not None and _row_project_base(row) != project_base:
        return False
    if providers is not None and row.get("provider") not in providers:
        return False
    if session_id is not None and row.get("session_id") != session_id:
        return False
    if (
        display_name is not None
        and display_name.casefold() not in str(row.get("display_name", "")).casefold()
    ):
        return False
    if extractable_only and row.get("extractable") is not True:
        return False
    if active_after is not None and not _last_activity_at_is_after(
        row.get("last_activity_at"), active_after
    ):
        return False
    if active_before is not None and not _last_activity_at_is_before(
        row.get("last_activity_at"), active_before
    ):
        return False
    return True


def select_materialization_row(
    row: dict[str, Any],
    *,
    uri: str | None = None,
    instances: tuple[str, ...] | None = None,
    provider_instance_fingerprint: str | None = None,
) -> dict[str, Any]:
    if uri is None and instances is None and provider_instance_fingerprint is None:
        return row
    matched = [
        version
        for version in archive_versions_for(row)
        if _version_matches_selector(
            version,
            uri=uri,
            instances=instances,
            provider_instance_fingerprint=provider_instance_fingerprint,
        )
    ]
    if len(matched) == 1:
        return matched[0]
    if not matched:
        return row
    identities = {_materialization_identity(version) for version in matched}
    if len(identities) == 1:
        return matched[0]
    raise CliError(
        "index selector matched multiple archived versions; add a more specific "
        "selector before materializing raw artifacts"
    )


def _version_matches_selector(
    row: dict[str, Any],
    *,
    uri: str | None,
    instances: tuple[str, ...] | None,
    provider_instance_fingerprint: str | None,
) -> bool:
    if uri is not None and row.get("uri") != uri:
        return False
    if instances is not None and row.get("instance") not in instances:
        return False
    if (
        provider_instance_fingerprint is not None
        and row.get("provider_instance_fingerprint") != provider_instance_fingerprint
    ):
        return False
    return True


def _materialization_identity(row: dict[str, Any]) -> str:
    return json.dumps(
        {
            "uri": row.get("uri"),
            "provider_instance_fingerprint": row.get("provider_instance_fingerprint"),
            "backing_artifacts": row.get("backing_artifacts"),
            "primary_backing_artifact": row.get("primary_backing_artifact"),
        },
        sort_keys=True,
        default=str,
    )


def sort_chatlas_index_rows(
    rows: list[dict[str, Any]], *, sort: str
) -> list[dict[str, Any]]:
    if sort == "newest":
        return sorted(
            rows,
            key=lambda row: chatlas_index_timestamp_sort_value(
                row.get("last_activity_at")
            ),
            reverse=True,
        )
    if sort == "oldest":
        return sorted(
            rows,
            key=lambda row: chatlas_index_timestamp_sort_value(
                row.get("last_activity_at")
            ),
        )
    return sorted(
        rows, key=lambda row: str(row.get("uri") or row.get("session_id") or "")
    )


def _last_activity_at_is_after(value: object, active_after: str) -> bool:
    timestamp = parse_chatlas_index_timestamp(value)
    threshold = parse_chatlas_index_timestamp(active_after)
    return timestamp is not None and threshold is not None and timestamp >= threshold


def _last_activity_at_is_before(value: object, active_before: str) -> bool:
    timestamp = parse_chatlas_index_timestamp(value)
    threshold = parse_chatlas_index_timestamp(active_before)
    return timestamp is not None and threshold is not None and timestamp <= threshold


def _row_project_path(row: dict[str, Any]) -> str | None:
    value = row.get("project_path")
    if not isinstance(value, str) or not value:
        return None
    return _normalized_project_selector_path(value)


def _row_project_base(row: dict[str, Any]) -> str | None:
    value = row.get("project_path")
    if not isinstance(value, str) or not value:
        return None
    return Path(value).name


def _normalized_project_selector_path(value: str | Path | None) -> str | None:
    if value is None:
        return None
    return str(Path(value).expanduser().resolve())


__all__ = [
    "chatlas_index_row_matches_logical",
    "chatlas_index_row_matches",
    "chatlas_index_query",
    "select_materialization_row",
    "select_one_chatlas_index_row",
    "sort_chatlas_index_rows",
]
