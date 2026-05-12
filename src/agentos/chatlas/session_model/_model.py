from __future__ import annotations

from pathlib import Path
from typing import Any

from agentos._core.errors import CliError
from agentos.chatlas.index_query import run_chatlas_index_query
from agentos.claude.session import ClaudeSession
from agentos.codex.session import CodexSession
from agentos.copilot.session import CopilotSession

from ._claude import _experimental_normalize_claude_session
from ._codex import _experimental_normalize_codex_session
from ._copilot import _experimental_normalize_copilot_session
from ._hashes import _session_content_hash, _session_identity_hash
from ._shared import _ExperimentalNormalizationResult, _jsonable_identity, _string_or_none
from ._views import _project_session_model_view

_SUPPORTED_EXPORT_PROVIDERS = ("codex", "claude-code", "copilot-cli")


def chatlas_export_session_model(
    *,
    query: str,
    providers: tuple[str, ...] | None = None,
    output_format: str = "json",
    view: str = "full",
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    if output_format != "json":
        raise CliError(f"unsupported chatlas export format: {output_format}")

    normalized_query = query.strip()
    if not normalized_query:
        raise CliError("query must not be empty")

    session = _select_export_index_row(
        query=normalized_query,
        providers=providers,
        chatlas_root=chatlas_root,
    )
    session_model = _build_session_model(session)
    return _project_session_model_view(session_model, view=view)


def _select_export_index_row(
    *,
    query: str,
    providers: tuple[str, ...] | None,
    chatlas_root: Path | None,
) -> dict[str, Any]:
    attempts = (
        ("uri", {"uri": query}),
        ("identity_hash", {"identity_hash": query}),
        ("session_id", {"session_id": query}),
        ("display_name", {"display_name": query}),
    )
    for matched_field, filters in attempts:
        payload = run_chatlas_index_query(
            providers=providers,
            limit=2,
            chatlas_root=chatlas_root,
            **filters,
        )
        matched_row_count = payload.get("matched_row_count")
        rows = payload.get("rows")
        if not isinstance(rows, list):
            raise CliError("Chatlas index query returned an invalid rows payload")
        if matched_row_count == 0:
            continue
        if matched_row_count == 1 and len(rows) == 1 and isinstance(rows[0], dict):
            return rows[0]
        candidates = _export_candidate_summary(rows)
        raise CliError(
            f"multiple Chatlas sessions matched query {query!r} by {matched_field}: {candidates}"
        )

    raise CliError(f"no indexed Chatlas session matched query {query!r}")


def _export_candidate_summary(rows: list[object]) -> str:
    candidates: list[str] = []
    for row in rows[:5]:
        if not isinstance(row, dict):
            continue
        identity = _string_or_none(row.get("uri")) or _string_or_none(row.get("session_id"))
        if identity is not None:
            candidates.append(identity)
    if not candidates:
        return "<no valid candidates returned>"
    return ", ".join(candidates)


def _build_session_model(session: dict[str, Any]) -> dict[str, object]:
    provider = _string_or_none(session.get("provider"))
    sources = _experimental_source_payloads(session)
    normalization_result = _experimental_normalize_provider_raw(session)
    normalization: dict[str, object] = {
        "provider": provider,
        "normalizer": normalization_result.normalizer,
        "version": 1,
        "source_mode": normalization_result.source_mode,
        "warnings": normalization_result.warnings,
        "unsupported_concepts": normalization_result.unsupported_concepts,
    }
    normalization.update(normalization_result.metadata)
    events = normalization_result.events
    session_payload = _experimental_session_payload(session)
    session_payload.update(_experimental_session_hashes(session, events=events))

    return {
        "class": "agentos.chatlas.session_model",
        "schema_version": 1,
        "session": session_payload,
        "agent_instance": _experimental_agent_instance_payload(session),
        "sources": sources,
        "chat": {
            "messages": _standard_records_payload(normalization_result.messages),
            "model_runs": _standard_records_payload(normalization_result.model_runs),
            "tool_invocations": _standard_records_payload(
                normalization_result.tool_invocations
            ),
            "events": events,
            "usage": _standard_records_payload(normalization_result.usage),
        },
        "normalization": normalization,
    }


def _experimental_normalize_provider_raw(
    session: dict[str, Any],
) -> _ExperimentalNormalizationResult:
    provider = _string_or_none(session.get("provider"))
    if provider is None:
        raise CliError(
            "chatlas export requires a provider-specific raw normalizer; "
            "session provider is missing"
        )
    if provider == "codex":
        codex_session = CodexSession.from_chatlas_session_payload(
            session,
            sources=_experimental_source_payloads(session),
        )
        if codex_session is not None:
            codex_result = _experimental_normalize_codex_session(codex_session)
            if codex_result is not None:
                return codex_result
        raise CliError("chatlas export could not normalize codex raw artifacts")
    if provider == "claude-code":
        claude_session = ClaudeSession.from_chatlas_session_payload(
            session,
            sources=_experimental_source_payloads(session),
        )
        if claude_session is not None:
            claude_result = _experimental_normalize_claude_session(claude_session)
            if claude_result is not None:
                return claude_result
        raise CliError("chatlas export could not normalize claude-code raw artifacts")
    if provider == "copilot-cli":
        copilot_session = CopilotSession.from_chatlas_session_payload(
            session,
            sources=_experimental_source_payloads(session),
        )
        if copilot_session is not None:
            copilot_result = _experimental_normalize_copilot_session(copilot_session)
            if copilot_result is not None:
                return copilot_result
        raise CliError("chatlas export could not normalize copilot-cli raw artifacts")

    raise CliError(
        "chatlas export has no provider-specific raw normalizer "
        f"for provider {provider!r}; supported providers: "
        f"{', '.join(_SUPPORTED_EXPORT_PROVIDERS)}"
    )


def _experimental_session_payload(session: dict[str, Any]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key in (
        "uri",
        "provider",
        "instance",
        "provider_instance_fingerprint",
        "session_id",
        "display_name",
        "display_name_field",
        "created_at",
        "updated_at",
    ):
        value = session.get(key)
        if value is not None:
            payload[key] = value
    return payload


def _experimental_session_hashes(
    session: dict[str, Any],
    *,
    events: list[dict[str, object]],
) -> dict[str, object]:
    provider = _string_or_none(session.get("provider"))
    session_id = _string_or_none(session.get("session_id"))
    if provider is None:
        raise CliError("chatlas export requires provider to compute identity_hash")
    if session_id is None:
        raise CliError("chatlas export requires session_id to compute identity_hash")
    return {
        "identity_hash": _session_identity_hash(
            provider=provider,
            provider_session_id=session_id,
        ),
        "content_hash": _session_content_hash(events=events),
    }


def _standard_records_payload(records: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        cleaned_record
        for record in records
        if isinstance((cleaned_record := _standard_record_payload(record)), dict)
    ]


def _standard_record_payload(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _standard_record_payload(item)
            for key, item in value.items()
            if key != "native"
        }
    if isinstance(value, list):
        return [_standard_record_payload(item) for item in value]
    return value


def _experimental_agent_instance_payload(session: dict[str, Any]) -> dict[str, object]:
    payload: dict[str, object] = {}
    provider = _string_or_none(session.get("provider"))
    instance = _string_or_none(session.get("instance"))
    fingerprint = _string_or_none(session.get("provider_instance_fingerprint"))
    if provider is not None:
        payload["provider_family"] = provider
    if instance is not None:
        payload["instance"] = instance
    if fingerprint is not None:
        payload["provider_instance_fingerprint"] = fingerprint
    return payload


def _experimental_source_payloads(session: dict[str, Any]) -> list[dict[str, object]]:
    artifacts = session.get("backing_artifacts")
    if not isinstance(artifacts, list):
        primary = session.get("primary_backing_artifact")
        artifacts = [primary] if isinstance(primary, dict) else []

    sources: list[dict[str, object]] = []
    seen: set[tuple[object, ...]] = set()
    for index, artifact in enumerate(artifacts, start=1):
        if not isinstance(artifact, dict):
            continue
        source = _experimental_source_payload(index=index, artifact=artifact)
        identity = (
            source.get("role"),
            source.get("storage_kind"),
            source.get("path"),
            _jsonable_identity(source.get("locator")),
        )
        if identity in seen:
            continue
        seen.add(identity)
        sources.append(source)
    return sources


def _experimental_source_payload(*, index: int, artifact: dict[str, Any]) -> dict[str, object]:
    payload: dict[str, object] = {
        "source_ref_id": f"source-{index}",
    }
    for key in (
        "role",
        "storage_kind",
        "path",
        "locator",
        "extractable",
    ):
        value = artifact.get(key)
        if value is not None:
            payload[key] = value
    return payload
