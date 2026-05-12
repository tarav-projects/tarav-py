from __future__ import annotations

import json
from typing import Any

from agentos._core.errors import CliError
from agentos.agent.extractors import extract_chat_session

from ._shared import *

def _experimental_clean_transcript_result(
    session: dict[str, Any],
    *,
    sources: list[dict[str, object]],
    normalizer: str,
) -> _ExperimentalNormalizationResult:
    warnings = [
        "chat messages were normalized from the clean transcript fallback",
        "raw replay events, tool execution structure, model-run boundaries, and reasoning details may be missing",
    ]
    unsupported_concepts = [
        "model_runs",
        "tool_invocations",
        "events",
    ]
    primary_artifact = _primary_backing_artifact(session)
    if primary_artifact is None:
        return _ExperimentalNormalizationResult(
            messages=[],
            model_runs=[],
            tool_invocations=[],
            events=[],
            usage=[],
            normalizer=normalizer,
            source_mode="session_metadata_only",
            warnings=[
                "no primary backing artifact is available for clean transcript fallback",
            ],
            unsupported_concepts=[
                "messages",
                *unsupported_concepts,
            ],
            metadata=_experimental_normalization_metadata(
                messages=[],
                model_runs=[],
                tool_invocations=[],
                events=[],
                usage=[],
                deferred_concepts=[],
            ),
        )

    primary_path = _string_or_none(primary_artifact.get("path"))
    if primary_path is None:
        return _ExperimentalNormalizationResult(
            messages=[],
            model_runs=[],
            tool_invocations=[],
            events=[],
            usage=[],
            normalizer=normalizer,
            source_mode="session_metadata_only",
            warnings=[
                "primary backing artifact has no path for clean transcript fallback",
            ],
            unsupported_concepts=[
                "messages",
                *unsupported_concepts,
            ],
            metadata=_experimental_normalization_metadata(
                messages=[],
                model_runs=[],
                tool_invocations=[],
                events=[],
                usage=[],
                deferred_concepts=[],
            ),
        )

    session_id = _string_or_none(session.get("session_id"))
    try:
        rendered = extract_chat_session(
            session_query=session_id,
            file_path=primary_path,
            output_format="jsonl",
            raw=False,
        )
    except (CliError, OSError, ValueError) as exc:
        return _ExperimentalNormalizationResult(
            messages=[],
            model_runs=[],
            tool_invocations=[],
            events=[],
            usage=[],
            normalizer=normalizer,
            source_mode="session_metadata_only",
            warnings=[
                f"clean transcript fallback failed: {exc}",
            ],
            unsupported_concepts=[
                "messages",
                *unsupported_concepts,
            ],
            metadata=_experimental_normalization_metadata(
                messages=[],
                model_runs=[],
                tool_invocations=[],
                events=[],
                usage=[],
                deferred_concepts=[],
            ),
        )

    source_ref_id = _source_ref_id_for_artifact(primary_artifact, sources=sources)
    try:
        messages = _messages_from_clean_transcript_jsonl(
            rendered,
            source_ref_id=source_ref_id,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        return _ExperimentalNormalizationResult(
            messages=[],
            model_runs=[],
            tool_invocations=[],
            events=[],
            usage=[],
            normalizer=normalizer,
            source_mode="session_metadata_only",
            warnings=[
                f"clean transcript fallback produced invalid jsonl: {exc}",
            ],
            unsupported_concepts=[
                "messages",
                *unsupported_concepts,
            ],
            metadata=_experimental_normalization_metadata(
                messages=[],
                model_runs=[],
                tool_invocations=[],
                events=[],
                usage=[],
                deferred_concepts=[],
            ),
        )
    if not messages:
        return _ExperimentalNormalizationResult(
            messages=[],
            model_runs=[],
            tool_invocations=[],
            events=[],
            usage=[],
            normalizer=normalizer,
            source_mode="clean_transcript_fallback",
            warnings=[
                "clean transcript fallback produced no messages",
                *warnings[1:],
            ],
            unsupported_concepts=unsupported_concepts,
            metadata=_experimental_normalization_metadata(
                messages=[],
                model_runs=[],
                tool_invocations=[],
                events=[],
                usage=[],
                deferred_concepts=[],
            ),
        )

    return _ExperimentalNormalizationResult(
        messages=messages,
        model_runs=[],
        tool_invocations=[],
        events=[],
        usage=[],
        normalizer=normalizer,
        source_mode="clean_transcript_fallback",
        warnings=warnings,
        unsupported_concepts=unsupported_concepts,
        metadata=_experimental_normalization_metadata(
            messages=messages,
            model_runs=[],
            tool_invocations=[],
            events=[],
            usage=[],
            deferred_concepts=[],
        ),
    )

def _messages_from_clean_transcript_jsonl(
    rendered: str,
    *,
    source_ref_id: str | None,
) -> list[dict[str, object]]:
    messages: list[dict[str, object]] = []
    for index, line in enumerate(rendered.splitlines(), start=1):
        if not line.strip():
            continue
        turn = json.loads(line)
        if not isinstance(turn, dict):
            continue
        role = _string_or_none(turn.get("role"))
        text = _string_or_none(turn.get("text"))
        timestamp = _string_or_none(turn.get("timestamp"))
        if role is None or text is None:
            continue
        message: dict[str, object] = {
            "message_id": f"message-{index}",
            "role": role,
            "content": [
                {
                    "type": "text",
                    "text": text,
                }
            ],
        }
        if timestamp is not None:
            message["timestamp"] = timestamp
        if source_ref_id is not None:
            message["source_refs"] = [{"source_ref_id": source_ref_id}]
        messages.append(message)
    return messages
