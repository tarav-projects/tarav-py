# $kw: --from Chatlas.Session.Model
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from tarav._core.errors import CliError
from tarav.agent.providers.codex.extractor import is_codex_rollout_path
from tarav.agent.session_utils import primary_transcript_artifact
from tarav.agent.providers.claude_code.session import ClaudeSession
from tarav.agent.providers.codex.session import CodexSession
from tarav.agent.providers.copilot_cli.session import CopilotSession

from ._claude import _normalize_claude_session
from ._codex import _normalize_codex_session
from ._copilot import _normalize_copilot_session
from .hashes import session_content_hash, session_identity_hash
from tarav.chatlas._payload_helpers import jsonable_identity, string_or_none
from .normalization import NormalizationResult
from ._views import _project_session_model_view

def build_chatlas_session_model_from_index_row(
    session: dict[str, Any],
    *,
    chatlas_root: Path | None = None,
    trust: str | None = None,
) -> dict[str, object]:


    from tarav.chatlas.normalization.session_assembler import assemble_session_model

    return assemble_session_model(
        session,
        normalization_result=_rooted_normalization_result(
            session, chatlas_root=chatlas_root, trust=trust
        ),
    )


def build_session_model_with_delta_state(
    session: dict[str, Any],
    *,
    chatlas_root: Path,
) -> tuple[dict[str, object], dict[str, Any] | None]:
    """Rooted build that also surfaces the producer-private delta resume state.

    For the artifact publisher only: the `Normalization.Delta.Checkpoint::Chatlas`
    is recorded in lockstep with the artifact write (`record_delta_checkpoint`),
    never on plain builds — checkpoint and artifact cannot drift apart."""
    from tarav.chatlas.normalization.session_assembler import assemble_session_model

    result = _rooted_normalization_result(session, chatlas_root=chatlas_root, trust=None)
    if result is None and string_or_none(session.get("provider")) == "claude-code":
        try:
            result = _normalize_provider_raw(session)
        except CliError:
            result = None
    model = assemble_session_model(session, normalization_result=result)
    delta_state = result.metadata.get("delta_state") if result is not None else None
    return model, delta_state if isinstance(delta_state, dict) else None


def record_delta_checkpoint(
    session: dict[str, Any],
    *,
    chatlas_root: Path,
    delta_state: dict[str, Any] | None,
) -> None:
    from tarav.chatlas.normalization.session_model.delta import (
        discard_delta_checkpoint,
        save_delta_checkpoint,
    )

    provider = string_or_none(session.get("provider"))
    session_id = string_or_none(session.get("session_id"))
    if provider is None or session_id is None:
        return
    source_path = _primary_transcript_path(session)
    if isinstance(delta_state, dict) and source_path is not None:
        save_delta_checkpoint(
            chatlas_root,
            provider=provider,
            session_id=session_id,
            source_path=source_path,
            delta_state=delta_state,
        )
    else:
        discard_delta_checkpoint(chatlas_root, provider=provider, session_id=session_id)


def _rooted_normalization_result(
    session: dict[str, Any],
    *,
    chatlas_root: Path | None,
    trust: str | None,
) -> NormalizationResult | None:



    if chatlas_root is None:
        return None

    from tarav.chatlas.normalization.session_model.delta import (
        claude_delta_normalization_result,
        current_trust_tier,
    )

    provider = string_or_none(session.get("provider"))
    session_id = string_or_none(session.get("session_id"))
    if provider != "claude-code" or session_id is None:
        return None
    try:
        return claude_delta_normalization_result(
            session,
            chatlas_root=chatlas_root,
            artifact_dir=_session_model_artifact_dir(session, chatlas_root),
            trust=trust or current_trust_tier(),
        )
    except Exception:
        return None


def _primary_transcript_path(session: dict[str, Any]) -> Path | None:
    artifact = primary_transcript_artifact(session)
    if artifact is None:
        return None
    path_text = string_or_none(artifact.get("path"))
    return Path(path_text) if path_text is not None else None


def _session_model_artifact_dir(session: dict[str, Any], chatlas_root: Path) -> Path:
    from tarav.chatlas.session_cache import session_model_cache_path

    return session_model_cache_path(session, chatlas_root=chatlas_root)


def project_chatlas_session_model_view(
    session_model: dict[str, Any],
    *,
    view: str,
    range_spec: str | None = None,
    contains: str | None = None,
    role: str | None = None,
    around: str | None = None,
    radius: int | None = None,
) -> dict[str, object]:
    return _project_session_model_view(
        session_model,
        view=view,
        range_spec=range_spec,
        contains=contains,
        role=role,
        around=around,
        radius=radius,
    )




_CHATLAS_SESSION_MODEL_SCHEMA_VERSION = 5


def validate_session_model_schema_version(session_model: dict[str, Any]) -> None:
    schema_version = session_model.get("schema_version")
    if schema_version != _CHATLAS_SESSION_MODEL_SCHEMA_VERSION:
        raise CliError(
            f"chatlas session_model schema_version={schema_version!r} is unsupported; "
            "reset the Chatlas session-model cache and run `tarav chatlas index redo`"
        )


def _normalize_provider_raw(
    session: dict[str, Any],
) -> NormalizationResult:
    provider = string_or_none(session.get("provider"))
    if provider is None:
        raise CliError(
            "chatlas views get requires a provider-specific raw normalizer; "
            "session provider is missing"
        )
    entry = _PROVIDER_NORMALIZERS.get(provider)
    if entry is None:
        raise CliError(
            "chatlas views get has no provider-specific raw normalizer "
            f"for provider {provider!r}; supported providers: "
            f"{', '.join(_PROVIDER_NORMALIZERS)}"
        )
    session_cls, normalize, failure_message = entry
    provider_session = session_cls.from_chatlas_session_payload(
        session,
        sources=_source_payloads(session),
    )
    if provider_session is not None:
        result = normalize(provider_session)
        if result is not None:
            return result
    raise CliError(failure_message(session))


def _codex_normalization_failure_message(session: dict[str, Any]) -> str:
    prefix = "chatlas views get could not normalize codex raw artifacts"
    session_id = string_or_none(session.get("session_id"))
    session_text = f" for session {session_id!r}" if session_id is not None else ""
    artifact = primary_transcript_artifact(session)
    if artifact is None:
        return f"{prefix}{session_text}: no primary transcript backing artifact"

    path_text = string_or_none(artifact.get("path"))
    if path_text is None:
        return f"{prefix}{session_text}: primary transcript artifact has no path"

    path = Path(path_text)
    if not path.exists():
        return f"{prefix}{session_text}: primary transcript artifact is missing: {path}"
    if not path.is_file():
        return f"{prefix}{session_text}: primary transcript artifact is not a file: {path}"
    try:
        if not is_codex_rollout_path(path):
            return (
                f"{prefix}{session_text}: primary transcript artifact is not a "
                f"recognized Codex rollout JSONL: {path}"
            )
    except OSError as exc:
        return f"{prefix}{session_text}: could not read primary transcript artifact {path}: {exc}"

    return (
        f"{prefix}{session_text}: recognized Codex rollout produced no normalizable "
        f"messages, events, model runs, or clean transcript fallback records: {path}"
    )


_PROVIDER_NORMALIZERS: dict[
    str,
    tuple[
        Any,
        Callable[[Any], NormalizationResult | None],
        Callable[[dict[str, Any]], str],
    ],
] = {
    "codex": (
        CodexSession,
        _normalize_codex_session,
        _codex_normalization_failure_message,
    ),
    "claude-code": (
        ClaudeSession,
        _normalize_claude_session,
        lambda session: "chatlas views get could not normalize claude-code raw artifacts",
    ),
    "copilot-cli": (
        CopilotSession,
        _normalize_copilot_session,
        lambda session: "chatlas views get could not normalize copilot-cli raw artifacts",
    ),
}


def _session_payload(session: dict[str, Any]) -> dict[str, object]:
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
        "last_activity_at",
    ):
        value = session.get(key)
        if value is not None:
            payload[key] = value
    return payload


def _session_hashes(
    session: dict[str, Any],
    *,
    events: list[dict[str, object]],
) -> dict[str, object]:
    provider = string_or_none(session.get("provider"))
    session_id = string_or_none(session.get("session_id"))
    if provider is None:
        raise CliError("chatlas views get requires provider to compute identity_hash")
    if session_id is None:
        raise CliError("chatlas views get requires session_id to compute identity_hash")
    return {
        "identity_hash": session_identity_hash(
            provider=provider,
            provider_session_id=session_id,
        ),
        "content_hash": session_content_hash(events=events),
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


def _agent_instance_payload(session: dict[str, Any]) -> dict[str, object]:
    payload: dict[str, object] = {}
    provider = string_or_none(session.get("provider"))
    instance = string_or_none(session.get("instance"))
    fingerprint = string_or_none(session.get("provider_instance_fingerprint"))
    if provider is not None:
        payload["provider_family"] = provider
    if instance is not None:
        payload["instance"] = instance
    if fingerprint is not None:
        payload["provider_instance_fingerprint"] = fingerprint
    return payload


def _source_payloads(session: dict[str, Any]) -> list[dict[str, object]]:
    artifacts = session.get("backing_artifacts")
    if not isinstance(artifacts, list):
        primary = session.get("primary_backing_artifact")
        artifacts = [primary] if isinstance(primary, dict) else []

    sources: list[dict[str, object]] = []
    seen: set[tuple[object, ...]] = set()
    for index, artifact in enumerate(artifacts, start=1):
        if not isinstance(artifact, dict):
            continue
        source = _source_payload(index=index, artifact=artifact)
        identity = (
            source.get("role"),
            source.get("storage_kind"),
            source.get("path"),
            jsonable_identity(source.get("locator")),
        )
        if identity in seen:
            continue
        seen.add(identity)
        sources.append(source)
    return sources


def _source_payload(*, index: int, artifact: dict[str, Any]) -> dict[str, object]:
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
