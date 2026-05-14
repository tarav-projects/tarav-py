from __future__ import annotations

from pathlib import Path
from typing import Any

from agentos.chatlas.index_query import chatlas_index_row_matches
from agentos.chatlas.index_query import sort_chatlas_index_rows
from agentos.chatlas.index_store import load_chatlas_session_index_rows
from agentos.chatlas.session_model import build_chatlas_session_model_from_index_row

_DEFAULT_LIMIT = 50
_DEFAULT_SCAN_LIMIT = 5000


def run_chatlas_query(
    *,
    uri: str | None = None,
    identity_hash: str | None = None,
    providers: tuple[str, ...] | None = None,
    session_id: str | None = None,
    display_name: str | None = None,
    extractable_only: bool = False,
    updated_after: str | None = None,
    sort: str = "lexical",
    scan_limit: int | None = None,
    limit: int | None = None,
    raw_contains: tuple[str, ...] | None = None,
    user_contains: tuple[str, ...] | None = None,
    assistant_contains: tuple[str, ...] | None = None,
    message_contains: tuple[str, ...] | None = None,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    index = load_chatlas_session_index_rows(chatlas_root=chatlas_root)
    filters = {
        "uri": uri,
        "identity_hash": identity_hash,
        "providers": list(providers) if providers is not None else None,
        "session_id": session_id,
        "display_name": display_name,
        "extractable": extractable_only,
        "updated_after": updated_after,
        "raw_contains": list(raw_contains) if raw_contains is not None else None,
        "user_contains": list(user_contains) if user_contains is not None else None,
        "assistant_contains": list(assistant_contains) if assistant_contains is not None else None,
        "message_contains": list(message_contains) if message_contains is not None else None,
    }
    index_matched_rows = [
        row
        for row in index.rows
        if chatlas_index_row_matches(
            row,
            uri=uri,
            identity_hash=identity_hash,
            providers=providers,
            instances=None,
            provider_instance_fingerprint=None,
            session_id=session_id,
            display_name=display_name,
            extractable_only=extractable_only,
            updated_after=updated_after,
        )
    ]
    sorted_rows = sort_chatlas_index_rows(index_matched_rows, sort=sort)
    effective_scan_limit = _DEFAULT_SCAN_LIMIT if scan_limit is None else scan_limit
    scanned_candidates = sorted_rows[:effective_scan_limit]
    filtered_rows = [
        row
        for row in scanned_candidates
        if _row_matches_raw_filters(row, raw_contains=raw_contains)
        and _row_matches_standard_model_filters(
            row,
            user_contains=user_contains,
            assistant_contains=assistant_contains,
            message_contains=message_contains,
        )
    ]
    effective_limit = _DEFAULT_LIMIT if limit is None else limit
    returned_rows = filtered_rows[:effective_limit]
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
        "rows": [_normalized_session_row(row) for row in returned_rows],
    }


def _row_matches_raw_filters(
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


def _row_matches_standard_model_filters(
    row: dict[str, Any],
    *,
    user_contains: tuple[str, ...] | None,
    assistant_contains: tuple[str, ...] | None,
    message_contains: tuple[str, ...] | None,
) -> bool:
    if not user_contains and not assistant_contains and not message_contains:
        return True
    try:
        session_model = build_chatlas_session_model_from_index_row(row)
    except Exception:
        return False
    user_texts = _visible_message_texts(session_model, roles={"user"})
    assistant_texts = _visible_message_texts(session_model, roles={"assistant"})
    message_texts = user_texts + assistant_texts
    return (
        _texts_match_all(user_texts, user_contains)
        and _texts_match_all(assistant_texts, assistant_contains)
        and _texts_match_all(message_texts, message_contains)
    )


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


def _visible_message_texts(
    session_model: dict[str, Any],
    *,
    roles: set[str],
) -> list[str]:
    chat = session_model.get("chat")
    if not isinstance(chat, dict):
        return []
    messages = chat.get("messages")
    if not isinstance(messages, list):
        return []
    texts: list[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        if message.get("role") not in roles:
            continue
        if message.get("visibility") != "conversation":
            continue
        text = _content_text(message.get("content"))
        if text:
            texts.append(text)
    return texts


def _content_text(value: object) -> str:
    if not isinstance(value, list):
        return ""
    return "\n".join(
        text
        for block in value
        if isinstance(block, dict)
        and isinstance((text := block.get("text")), str)
    )


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
        "uri": _string_or_none(row.get("uri")),
        "provider": _string_or_none(row.get("provider")),
        "session_id": _string_or_none(row.get("session_id")),
        "updated_at": _string_or_none(row.get("updated_at")),
        "home": _string_or_none(row.get("home")),
        "project_path": _string_or_none(row.get("project_path")),
    }


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str):
        return value
    return None


__all__ = ["run_chatlas_query"]
