from __future__ import annotations

from pathlib import Path
from typing import Any

from agentos._core.errors import CliError
from agentos.chatlas.core import chatlas_query

from ._claude import _experimental_normalize_claude_code_raw_session
from ._codex import _experimental_normalize_codex_raw_rollout
from ._copilot import _experimental_normalize_copilot_cli_raw_events
from ._shared import *

def chatlas_experimental_export_session_model(
    *,
    query: str,
    providers: tuple[str, ...] | None = None,
    output_format: str = "json",
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    if output_format != "json":
        raise CliError(f"unsupported experimental export format: {output_format}")

    normalized_query = query.strip()
    if not normalized_query:
        raise CliError("query must not be empty")

    payload = chatlas_query(
        query=normalized_query,
        providers=providers,
        chatlas_root=chatlas_root,
        include_artifacts=True,
    )
    sessions = payload.get("sessions")
    if not isinstance(sessions, list):
        raise CliError("Chatlas query returned an invalid sessions payload")
    if not sessions:
        raise CliError(f"no normalized Chatlas session matched query {query}")
    if len(sessions) > 1:
        choices = ", ".join(
            str(session.get("uri"))
            for session in sessions[:5]
            if isinstance(session, dict)
        )
        raise CliError(f"multiple Chatlas sessions matched query {query}: {choices}")

    session = sessions[0]
    if not isinstance(session, dict):
        raise CliError("Chatlas query returned an invalid session payload")

    return _build_experimental_session_model(session)

def _build_experimental_session_model(session: dict[str, Any]) -> dict[str, object]:
    provider = _string_or_none(session.get("provider"))
    sources = _experimental_source_payloads(session)
    normalization_result = _experimental_normalize_provider_raw(
        session,
        sources=sources,
    )
    normalization: dict[str, object] = {
        "provider": provider,
        "normalizer": normalization_result.normalizer,
        "version": 1,
        "source_mode": normalization_result.source_mode,
        "warnings": normalization_result.warnings,
        "unsupported_concepts": normalization_result.unsupported_concepts,
    }
    normalization.update(normalization_result.metadata)

    return {
        "class": "agentos.chatlas.experimental.session_model",
        "schema_version": 1,
        "experimental": True,
        "session": _experimental_session_payload(session),
        "agent_instance": _experimental_agent_instance_payload(session),
        "sources": sources,
        "chat": {
            "messages": _standard_records_payload(normalization_result.messages),
            "model_runs": _standard_records_payload(normalization_result.model_runs),
            "tool_invocations": _standard_records_payload(
                normalization_result.tool_invocations
            ),
            "events": normalization_result.events,
            "usage": _standard_records_payload(normalization_result.usage),
        },
        "normalization": normalization,
    }

def _experimental_normalize_provider_raw(
    session: dict[str, Any],
    *,
    sources: list[dict[str, object]],
) -> _ExperimentalNormalizationResult:
    provider = _string_or_none(session.get("provider"))
    if provider is None:
        raise CliError(
            "experimental session model export requires a provider-specific raw normalizer; "
            "session provider is missing"
        )
    if provider == "codex":
        codex_result = _experimental_normalize_codex_raw_rollout(
            session,
            sources=sources,
        )
        if codex_result is not None:
            return codex_result
        raise CliError(
            "experimental session model export could not normalize codex raw artifacts"
        )
    if provider == "claude-code":
        claude_result = _experimental_normalize_claude_code_raw_session(
            session,
            sources=sources,
        )
        if claude_result is not None:
            return claude_result
        raise CliError(
            "experimental session model export could not normalize claude-code raw artifacts"
        )
    if provider == "copilot-cli":
        copilot_result = _experimental_normalize_copilot_cli_raw_events(
            session,
            sources=sources,
        )
        if copilot_result is not None:
            return copilot_result
        raise CliError(
            "experimental session model export could not normalize copilot-cli raw artifacts"
        )

    raise CliError(
        "experimental session model export has no provider-specific raw normalizer "
        f"for provider {provider}"
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
