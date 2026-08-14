# $kw: --from Chatlas.Query.Surface
from __future__ import annotations

from pathlib import Path
from typing import Any

from tarav.chatlas._payload_helpers import string_or_none
from tarav.chatlas.annotations import read_shard_annotations
from tarav.chatlas.chat_index import chat_index_discovery
from tarav.chatlas.normalization.session_model.messages import visible_message_texts
from tarav.chatlas.index_query import chatlas_index_row_matches
from tarav.chatlas.index_query import sort_chatlas_index_rows
from tarav.chatlas.index_store import load_chatlas_session_index_rows
from tarav.chatlas.time_interface import format_local_timestamp
from tarav.chatlas.views import load_chatlas_session_model
from tarav.chatlas.normalization.session_model.file_touch import file_touch_invocations, tool_contains_invocations

_DEFAULT_LIMIT = 50
_DEFAULT_SCAN_LIMIT = 5000


def chatlas_query(
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
    active_before: str | None = None,
    sort: str = "lexical",
    scan_limit: int | None = None,
    limit: int | None = None,
    raw_contains: tuple[str, ...] | None = None,
    user_contains: tuple[str, ...] | None = None,
    assistant_contains: tuple[str, ...] | None = None,
    message_contains: tuple[str, ...] | None = None,
    file_read: tuple[str, ...] | None = None,
    file_write: tuple[str, ...] | None = None,
    file_touched: tuple[str, ...] | None = None,
    tool_contains: tuple[str, ...] | None = None,
    tool_name: str | None = None,
    min_user_turns: int | None = None,
    tags: tuple[str, ...] | None = None,
    without_tags: tuple[str, ...] | None = None,
    chatlas_root: Path | None = None,
    row_shape: str = "compact",
) -> dict[str, object]:
    if row_shape not in {"compact", "full"}:
        raise ValueError(f"unsupported Chatlas query row_shape: {row_shape}")
    index = load_chatlas_session_index_rows(chatlas_root=chatlas_root)
    filters = {
        "uri": uri,
        "identity_hash": identity_hash,
        "project": str(Path(project).expanduser().resolve()) if project is not None else None,
        "project_base": project_base,
        "providers": list(providers) if providers is not None else None,
        "instances": list(instances) if instances is not None else None,
        "provider_instance_fingerprint": provider_instance_fingerprint,
        "session_id": session_id,
        "display_name": display_name,
        "extractable": extractable_only,
        "active_after": active_after,
        "active_before": active_before,
        "raw_contains": list(raw_contains) if raw_contains is not None else None,
        "user_contains": list(user_contains) if user_contains is not None else None,
        "assistant_contains": list(assistant_contains) if assistant_contains is not None else None,
        "message_contains": list(message_contains) if message_contains is not None else None,
        "file_read": list(file_read) if file_read is not None else None,
        "file_write": list(file_write) if file_write is not None else None,
        "file_touched": list(file_touched) if file_touched is not None else None,
        "tool_contains": list(tool_contains) if tool_contains is not None else None,
        "tool_name": tool_name,
        "min_user_turns": min_user_turns,
        "tags": list(tags) if tags is not None else None,
        "without_tags": list(without_tags) if without_tags is not None else None,
    }
    index_matched_rows = [
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
            active_before=active_before,
        )
    ]
    sorted_rows = sort_chatlas_index_rows(index_matched_rows, sort=sort)
    effective_scan_limit = _DEFAULT_SCAN_LIMIT if scan_limit is None else scan_limit
    scanned_candidates = sorted_rows[:effective_scan_limit]
    annotation_shard_cache: dict[str, dict[str, dict[str, Any]]] = {}
    filtered_rows = [
        row
        for row in scanned_candidates
        if row_matches_raw_filters(row, raw_contains=raw_contains)
        and row_matches_summary_filters(row, min_user_turns=min_user_turns)
        and row_matches_standard_model_filters(
            row,
            user_contains=user_contains,
            assistant_contains=assistant_contains,
            message_contains=message_contains,
            file_read=file_read,
            file_write=file_write,
            file_touched=file_touched,
            tool_contains=tool_contains,
            tool_name=tool_name,
        )
        and row_matches_annotation_filters(
            row,
            tags=tags,
            without_tags=without_tags,
            shard_cache=annotation_shard_cache,
            chatlas_root=chatlas_root,
        )
    ]
    effective_limit = _DEFAULT_LIMIT if limit is None else limit
    returned_rows = filtered_rows[:effective_limit]
    result_rows: list[dict[str, object]] = []
    for row in returned_rows:
        out: dict[str, object] = dict(row) if row_shape == "full" else _normalized_session_row(row)
        row_identity_hash = row.get("identity_hash")
        if isinstance(row_identity_hash, str) and row_identity_hash:
            out["chat_index"] = chat_index_discovery(
                row_identity_hash,
                chatlas_root=index.chatlas_root,
            )
        result_rows.append(out)
    return {
        "status": "ok",
        "command": "chatlas query",
        "chatlas_root": str(index.chatlas_root),
        "session_index_root": str(index.session_index_root),
        "filters": filters,
        "sort": sort,
        "scan_limit": effective_scan_limit,
        "limit": effective_limit,
        "partition_count": index.partition_count,
        "scanned_row_count": index.scanned_row_count,
        "skipped_row_count": index.skipped_row_count,
        "index_matched_row_count": len(index_matched_rows),
        "candidate_row_count": len(scanned_candidates),
        "query_matched_row_count": len(filtered_rows),
        "returned_row_count": len(returned_rows),
        "rows": result_rows,
    }


def row_matches_raw_filters(
    row: dict[str, Any],
    *,
    raw_contains: tuple[str, ...] | None,
) -> bool:
    if not raw_contains:
        return True
    artifact_texts = list(_raw_artifact_texts(row))
    return all(
        any(_contains_text(artifact_text, expected) for artifact_text in artifact_texts)
        for expected in raw_contains
    )


def row_matches_standard_model_filters(
    row: dict[str, Any],
    *,
    user_contains: tuple[str, ...] | None,
    assistant_contains: tuple[str, ...] | None,
    message_contains: tuple[str, ...] | None,
    file_read: tuple[str, ...] | None = None,
    file_write: tuple[str, ...] | None = None,
    file_touched: tuple[str, ...] | None = None,
    tool_contains: tuple[str, ...] | None = None,
    tool_name: str | None = None,
) -> bool:
    file_filters = (
        [("read", path) for path in file_read or ()]
        + [("write", path) for path in file_write or ()]
        + [("touched", path) for path in file_touched or ()]
    )
    if (
        not user_contains
        and not assistant_contains
        and not message_contains
        and not file_filters
        and not tool_contains
        and tool_name is None
    ):
        return True
    try:
        session_model = load_chatlas_session_model(row)
    except Exception:
        return False
    user_texts = visible_message_texts(session_model, normal_turn_kinds={"user"})
    assistant_texts = visible_message_texts(session_model, producer_types={"assistant"})
    message_texts = user_texts + assistant_texts
    return (
        _texts_match_all(user_texts, user_contains)
        and _texts_match_all(assistant_texts, assistant_contains)
        and _texts_match_all(message_texts, message_contains)
        and all(
            file_touch_invocations(session_model, path=path, mode=mode)
            for mode, path in file_filters
        )
        and all(
            tool_contains_invocations(session_model, text=needle, tool_name=tool_name)
            for needle in tool_contains or ()
        )
        and (
            tool_name is None
            or bool(tool_contains)
            or bool(tool_contains_invocations(session_model, text='', tool_name=tool_name))
        )
    )


def row_matches_annotation_filters(
    row: dict[str, Any],
    *,
    tags: tuple[str, ...] | None,
    without_tags: tuple[str, ...] | None,
    shard_cache: dict[str, dict[str, dict[str, Any]]],
    chatlas_root: Path | None,
) -> bool:
    if not tags and not without_tags:
        return True
    identity_hash = row.get("identity_hash")
    if not isinstance(identity_hash, str) or not identity_hash:
        return not tags
    prefix = identity_hash[:2].lower()
    if prefix not in shard_cache:
        shard_cache[prefix] = read_shard_annotations(prefix, chatlas_root=chatlas_root)
    session_annotations = shard_cache[prefix].get(identity_hash, {})
    row_tags_value = session_annotations.get("tags")
    row_tags: list[str] = row_tags_value if isinstance(row_tags_value, list) else []
    if tags and not all(tag in row_tags for tag in tags):
        return False
    if without_tags and any(tag in row_tags for tag in without_tags):
        return False
    return True


def row_matches_summary_filters(
    row: dict[str, Any],
    *,
    min_user_turns: int | None,
) -> bool:
    if min_user_turns is None:
        return True
    summary = row.get("summary")
    if not isinstance(summary, dict):
        return False
    user_turn_count = summary.get("visible_user_turn_count")
    return isinstance(user_turn_count, int) and user_turn_count >= min_user_turns


def _raw_artifact_texts(row: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    for artifact in _backing_artifacts(row):
        path_value = artifact.get("path")
        if not isinstance(path_value, str):
            continue
        try:
            texts.append(Path(path_value).read_text(encoding="utf-8"))
        except OSError:
            continue
    return texts


def _backing_artifacts(row: dict[str, Any]) -> list[dict[str, Any]]:
    artifacts = row.get("backing_artifacts")
    if isinstance(artifacts, list):
        return [artifact for artifact in artifacts if isinstance(artifact, dict)]
    primary = row.get("primary_backing_artifact")
    if isinstance(primary, dict):
        return [primary]
    return []


def _texts_match_all(texts: list[str], expected_values: tuple[str, ...] | None) -> bool:
    if not expected_values:
        return True
    return all(
        any(_contains_text(text, expected) for text in texts)
        for expected in expected_values
    )


def _contains_text(text: str, expected: str) -> bool:
    return expected.casefold() in text.casefold()


def _normalized_session_row(row: dict[str, Any]) -> dict[str, object]:
    return {
        "uri": string_or_none(row.get("uri")),
        "provider": string_or_none(row.get("provider")),
        "instance": string_or_none(row.get("instance")),
        "identity_hash": string_or_none(row.get("identity_hash")),
        "session_id": string_or_none(row.get("session_id")),
        "last_activity_at": string_or_none(row.get("last_activity_at")),
        "home": string_or_none(row.get("home")),
        "project_path": string_or_none(row.get("project_path")),
        "summary": row.get("summary") if isinstance(row.get("summary"), dict) else None,
    }


__all__ = [
    "chatlas_query",
    "format_chatlas_query_text",
    "row_matches_annotation_filters",
    "row_matches_raw_filters",
    "row_matches_standard_model_filters",
    "row_matches_summary_filters",
]


def format_chatlas_query_text(payload: dict[str, Any]) -> str:
    rows = payload.get("rows")
    rows = rows if isinstance(rows, list) else []
    if not rows:
        return "no sessions matched the query"
    lines: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        identity = str(row.get("identity_hash") or "")
        last_activity = row.get("last_activity_at")
        head = "  ".join(
            part
            for part in (
                identity[:12],
                str(row.get("provider") or ""),
                str(row.get("session_id") or ""),
                format_local_timestamp(last_activity) if last_activity else "",
            )
            if part
        )
        lines.append(head)
        for label, key in (("project", "project_path"), ("summary", "summary")):
            value = row.get(key)
            if isinstance(value, str) and value:
                lines.append(f"    {label}: {value}")
        lines.append("")
    returned = payload.get("returned_row_count")
    matched = payload.get("query_matched_row_count")
    lines.append(f"{returned} of {matched} matching sessions")
    return "\n".join(lines)
