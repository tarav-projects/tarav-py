# $kw: ^agentos-provider-extraction --from Agent.Navigable.Codebase --note [DF] provider transcript extraction is selected from the canonical provider adapter registry --supp ^c20260811-62u
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from agentos._core.errors import CliError
from agentos.agent.sessions import resolve_chat_sessions
from agentos.agent.providers.claude_code.extractor import (
    extract_claude_code_chat_session_from_path,
    is_claude_code_session_path,
)
from agentos.agent.providers.copilot_cli.extractor import (
    extract_copilot_cli_chat_session_from_path,
    infer_copilot_cli_session_id_from_path,
    is_copilot_cli_session_path,
)
from agentos.agent.providers.codex.extractor import (
    extract_codex_chat_session_from_path,
    is_codex_rollout_path,
)
from agentos.agent.providers.gemini_cli.extractor import (
    extract_gemini_cli_chat_session_from_path,
    infer_gemini_cli_session_id_from_path,
    is_gemini_cli_session_path,
)
from agentos.agent.providers.opencode.extractor import (
    extract_opencode_chat_session_from_path,
    infer_opencode_session_id_from_path,
    is_opencode_session_path,
)
from agentos.agent.providers.pi.extractor import (
    extract_pi_chat_session_from_path,
    infer_pi_session_id_from_path,
    is_pi_session_path,
)
from agentos.agent.providers.openclaw.extractor import (
    extract_openclaw_chat_session_from_path,
    infer_openclaw_session_id_from_path,
    is_openclaw_session_path,
)
from agentos.agent.session_refs import BackingArtifact
from agentos.agent.sessions import ProviderSessionRefEntry


ProviderSessionExtractor = Callable[..., str]
ProviderSessionArtifactProbe = Callable[[Path], bool]


@dataclass(frozen=True)
class ProviderSessionExtractorSpec:
    provider: str
    probe_artifact_path: ProviderSessionArtifactProbe
    extract_from_path: ProviderSessionExtractor
    infer_session_id_from_path: Callable[[Path], str | None] | None = None


@dataclass(frozen=True)
class ResolvedProviderSessionExtractTarget:
    extractor: ProviderSessionExtractorSpec
    artifact_path: Path
    resolved_session_id: str | None
    session: ProviderSessionRefEntry | None = None
    backing_artifact: BackingArtifact | None = None


_PROVIDER_SESSION_EXTRACTORS: dict[str, ProviderSessionExtractorSpec] = {
    "claude-code": ProviderSessionExtractorSpec(
        provider="claude-code",
        probe_artifact_path=is_claude_code_session_path,
        extract_from_path=extract_claude_code_chat_session_from_path,
    ),
    "copilot-cli": ProviderSessionExtractorSpec(
        provider="copilot-cli",
        probe_artifact_path=is_copilot_cli_session_path,
        extract_from_path=extract_copilot_cli_chat_session_from_path,
        infer_session_id_from_path=infer_copilot_cli_session_id_from_path,
    ),
    "codex": ProviderSessionExtractorSpec(
        provider="codex",
        probe_artifact_path=is_codex_rollout_path,
        extract_from_path=extract_codex_chat_session_from_path,
    ),
    "gemini-cli": ProviderSessionExtractorSpec(
        provider="gemini-cli",
        probe_artifact_path=is_gemini_cli_session_path,
        extract_from_path=extract_gemini_cli_chat_session_from_path,
        infer_session_id_from_path=infer_gemini_cli_session_id_from_path,
    ),
    "opencode": ProviderSessionExtractorSpec(
        provider="opencode",
        probe_artifact_path=is_opencode_session_path,
        extract_from_path=extract_opencode_chat_session_from_path,
        infer_session_id_from_path=infer_opencode_session_id_from_path,
    ),
    "pi": ProviderSessionExtractorSpec(
        provider="pi",
        probe_artifact_path=is_pi_session_path,
        extract_from_path=extract_pi_chat_session_from_path,
        infer_session_id_from_path=infer_pi_session_id_from_path,
    ),
    "openclaw": ProviderSessionExtractorSpec(
        provider="openclaw",
        probe_artifact_path=is_openclaw_session_path,
        extract_from_path=extract_openclaw_chat_session_from_path,
        infer_session_id_from_path=infer_openclaw_session_id_from_path,
    ),
}


def extract_chat_session(
    *,
    session_query: str | None,
    file_path: str | None = None,
    output_format: str = "jsonl",
    raw: bool = False,
    start_path: Path | str = ".",
) -> str:
    target = _resolve_chat_session_extract_target(
        session_query=session_query,
        file_path=file_path,
        start_path=start_path,
    )
    return target.extractor.extract_from_path(
        path=target.artifact_path,
        session_id=target.resolved_session_id,
        output_format=output_format,
        raw=raw,
    )


def _resolve_chat_session_extract_target(
    *,
    session_query: str | None,
    file_path: str | None,
    start_path: Path | str,
) -> ResolvedProviderSessionExtractTarget:
    if file_path is not None:
        return _resolve_extract_target_from_backing_artifact(
            file_path=file_path,
            session_query=session_query,
        )

    requested_session_query = session_query
    if requested_session_query is None:
        raise CliError("session query is required unless --file is provided")

    supported_candidates: list[ResolvedProviderSessionExtractTarget] = []
    unsupported_providers: set[str] = set()
    seen_candidates: set[tuple[str, Path]] = set()

    for session in resolve_chat_sessions(requested_session_query, start_path=start_path):
        extractor = _PROVIDER_SESSION_EXTRACTORS.get(session.provider)
        if extractor is None:
            unsupported_providers.add(session.provider)
            continue

        candidate = _select_session_extract_target(session, extractor=extractor)
        if candidate is None:
            continue

        candidate_key = (session.provider, candidate.artifact_path)
        if candidate_key in seen_candidates:
            continue
        seen_candidates.add(candidate_key)
        supported_candidates.append(candidate)

    if len(supported_candidates) == 1:
        return supported_candidates[0]

    if len(supported_candidates) > 1:
        paths = ", ".join(str(candidate.artifact_path) for candidate in supported_candidates)
        raise CliError(
            f"multiple extractable backing artifacts found for query {requested_session_query}: {paths}"
        )

    if unsupported_providers:
        providers = ", ".join(sorted(unsupported_providers))
        raise CliError(
            f"session found, but no extractor is implemented for provider(s): {providers}"
        )

    raise CliError(f"no extractable backing artifact found for query {requested_session_query}")


def _resolve_extract_target_from_backing_artifact(
    *,
    file_path: str,
    session_query: str | None,
) -> ResolvedProviderSessionExtractTarget:
    path = Path(file_path).expanduser().resolve()
    if not path.exists():
        raise CliError(f"backing artifact does not exist: {path}")
    if not path.is_file():
        raise CliError(f"backing artifact path is not a file: {path}")

    extractor, inferred_session_id = _infer_extractor_from_backing_artifact_path(path)
    resolved_session_id = session_query or inferred_session_id
    if extractor.provider == "opencode" and path.name == "opencode.db" and resolved_session_id is None:
        raise CliError(f"session id is required when extracting from backing artifact: {path}")

    return ResolvedProviderSessionExtractTarget(
        extractor=extractor,
        artifact_path=path,
        resolved_session_id=resolved_session_id,
    )


def _select_session_extract_target(
    session: ProviderSessionRefEntry,
    *,
    extractor: ProviderSessionExtractorSpec,
) -> ResolvedProviderSessionExtractTarget | None:
    for backing_artifact in session.backing_artifacts():
        if not _backing_artifact_matches_extractor(backing_artifact, extractor=extractor):
            continue

        return ResolvedProviderSessionExtractTarget(
            extractor=extractor,
            artifact_path=backing_artifact.path,
            resolved_session_id=session.session_id,
            session=session,
            backing_artifact=backing_artifact,
        )

    return None


def _backing_artifact_matches_extractor(
    backing_artifact: BackingArtifact,
    *,
    extractor: ProviderSessionExtractorSpec,
) -> bool:
    path = backing_artifact.path
    if not path.exists() or not path.is_file():
        return False
    return extractor.probe_artifact_path(path)


def _infer_extractor_from_backing_artifact_path(path: Path) -> tuple[ProviderSessionExtractorSpec, str | None]:
    matching_extractors = [
        extractor
        for extractor in _PROVIDER_SESSION_EXTRACTORS.values()
        if extractor.probe_artifact_path(path)
    ]

    if len(matching_extractors) == 1:
        extractor = matching_extractors[0]
        inferred_session_id = None
        if extractor.infer_session_id_from_path is not None:
            inferred_session_id = extractor.infer_session_id_from_path(path)
        return extractor, inferred_session_id

    if len(matching_extractors) > 1:
        providers = ", ".join(sorted(extractor.provider for extractor in matching_extractors))
        raise CliError(
            f"multiple extractors match backing artifact provenance for {path}: {providers}"
        )

    raise CliError(f"unable to infer extractor from backing artifact provenance: {path}")


__all__ = [
    "extract_chat_session",
]

