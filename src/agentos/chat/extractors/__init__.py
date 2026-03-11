from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from agentos._core.errors import CliError
from agentos.chat.core import resolve_chat_sessions
from agentos.chat.extractors.claude_code import (
    extract_claude_code_chat_session_from_path,
    is_claude_code_session_path,
)
from agentos.chat.extractors.copilot_cli import (
    extract_copilot_cli_chat_session_from_path,
    infer_copilot_cli_session_id_from_path,
    is_copilot_cli_session_path,
)
from agentos.chat.extractors.codex import (
    extract_codex_chat_session_from_path,
    is_codex_rollout_path,
)
from agentos.chat.extractors.gemini_cli import (
    extract_gemini_cli_chat_session_from_path,
    infer_gemini_cli_session_id_from_path,
    is_gemini_cli_session_path,
)
from agentos.chat.extractors.opencode import (
    extract_opencode_chat_session_from_path,
    infer_opencode_session_id_from_path,
    is_opencode_session_path,
)
from agentos.chat.extractors.openclaw import (
    extract_openclaw_chat_session_from_path,
    infer_openclaw_session_id_from_path,
    is_openclaw_session_path,
)


ChatSessionExtractor = Callable[..., str]
ChatSessionArtifactProbe = Callable[[Path], bool]


@dataclass(frozen=True)
class ChatSessionExtractorSpec:
    provider: str
    probe_artifact_path: ChatSessionArtifactProbe
    extract_from_path: ChatSessionExtractor
    infer_session_id_from_path: Callable[[Path], str | None] | None = None


_CHAT_SESSION_EXTRACTORS: dict[str, ChatSessionExtractorSpec] = {
    "claude-code": ChatSessionExtractorSpec(
        provider="claude-code",
        probe_artifact_path=is_claude_code_session_path,
        extract_from_path=extract_claude_code_chat_session_from_path,
    ),
    "copilot-cli": ChatSessionExtractorSpec(
        provider="copilot-cli",
        probe_artifact_path=is_copilot_cli_session_path,
        extract_from_path=extract_copilot_cli_chat_session_from_path,
        infer_session_id_from_path=infer_copilot_cli_session_id_from_path,
    ),
    "codex": ChatSessionExtractorSpec(
        provider="codex",
        probe_artifact_path=is_codex_rollout_path,
        extract_from_path=extract_codex_chat_session_from_path,
    ),
    "gemini-cli": ChatSessionExtractorSpec(
        provider="gemini-cli",
        probe_artifact_path=is_gemini_cli_session_path,
        extract_from_path=extract_gemini_cli_chat_session_from_path,
        infer_session_id_from_path=infer_gemini_cli_session_id_from_path,
    ),
    "opencode": ChatSessionExtractorSpec(
        provider="opencode",
        probe_artifact_path=is_opencode_session_path,
        extract_from_path=extract_opencode_chat_session_from_path,
        infer_session_id_from_path=infer_opencode_session_id_from_path,
    ),
    "openclaw": ChatSessionExtractorSpec(
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
) -> str:
    extractor, artifact_path, resolved_session_id = _resolve_chat_session_extractor(
        session_query=session_query,
        file_path=file_path,
    )
    return extractor.extract_from_path(
        path=artifact_path,
        session_id=resolved_session_id,
        output_format=output_format,
        raw=raw,
    )


def _resolve_chat_session_extractor(
    *,
    session_query: str | None,
    file_path: str | None,
) -> tuple[ChatSessionExtractorSpec, Path, str | None]:
    if file_path is not None:
        path = Path(file_path).expanduser().resolve()
        if not path.exists():
            raise CliError(f"file does not exist: {path}")
        if not path.is_file():
            raise CliError(f"path is not a file: {path}")
        extractor, inferred_session_id = _infer_extractor_from_artifact_path(path)
        return extractor, path, session_query or inferred_session_id

    requested_session_query = session_query
    if requested_session_query is None:
        raise CliError("session query is required unless --file is provided")

    supported_candidates: list[tuple[ChatSessionExtractorSpec, Path, str]] = []
    unsupported_providers: set[str] = set()
    seen_candidates: set[tuple[str, Path]] = set()

    for session in resolve_chat_sessions(requested_session_query):
        provider = session.provider
        extractor = _CHAT_SESSION_EXTRACTORS.get(provider)
        if extractor is None:
            unsupported_providers.add(provider)
            continue

        artifact_path = session.primary_artifact_path()
        if artifact_path is None or not artifact_path.is_file():
            continue
        if not extractor.probe_artifact_path(artifact_path):
            continue

        candidate_key = (provider, artifact_path)
        if candidate_key in seen_candidates:
            continue
        seen_candidates.add(candidate_key)
        supported_candidates.append((extractor, artifact_path, session.session_id))

    if len(supported_candidates) == 1:
        return supported_candidates[0]

    if len(supported_candidates) > 1:
        paths = ", ".join(str(path) for _, path, _ in supported_candidates)
        raise CliError(
            f"multiple extractable session artifacts found for query {requested_session_query}: {paths}"
        )

    if unsupported_providers:
        providers = ", ".join(sorted(unsupported_providers))
        raise CliError(
            f"session found, but no extractor is implemented for provider(s): {providers}"
        )

    raise CliError(f"no extractable session artifact found for query {requested_session_query}")


def _infer_extractor_from_artifact_path(path: Path) -> tuple[ChatSessionExtractorSpec, str | None]:
    matching_extractors = [
        extractor
        for extractor in _CHAT_SESSION_EXTRACTORS.values()
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
        raise CliError(f"multiple extractors match file provenance for {path}: {providers}")

    raise CliError(f"unable to infer extractor from file provenance: {path}")


__all__ = [
    "extract_chat_session",
]
