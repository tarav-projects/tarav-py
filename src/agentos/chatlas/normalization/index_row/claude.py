"""claude-code `Raw.Normalizer`s for the index-row target.

Identity is read from the first JSONL record; `project_path` scans for the first record
carrying a `cwd` (fixing the `project_path: null` bug where a leading non-message record
with no `cwd` zeroed the field); `native.cwd` still mirrors the raw first record.
"""

from __future__ import annotations

import json
from pathlib import Path

from agentos._core.errors import CliError

from . import _raw
from .context import NormalizerContext
from .fragment import CREATED_AT_CANDIDATES_KEY, LAST_ACTIVITY_AT_CANDIDATES_KEY, ModelFragment


def claude_identity(ctx: NormalizerContext) -> ModelFragment:
    transcript = ctx.primary_transcript()
    if transcript is None:
        return {}
    first = ctx.first_jsonl_object(transcript.path)
    session_id = (
        _raw.string_or_none(first.get("sessionId")) if first is not None else None
    ) or transcript.path.stem
    return {"session_id": session_id}


def claude_cwd(ctx: NormalizerContext) -> ModelFragment:
    transcript = ctx.primary_transcript()
    if transcript is None:
        return {"project_path": None}
    # project_path: the first record carrying a cwd (524 fix). The original bug read
    # record 0 only, so a leading non-message record with no cwd gave project_path null.
    fragment: ModelFragment = {
        "project_path": _raw.read_first_jsonl_value(transcript.path, "cwd")
    }
    # native mirrors the raw first record (the session_ref's native metadata) — only
    # project_path moves with the fix.
    first = ctx.first_jsonl_object(transcript.path)
    first_cwd = _raw.string_or_none(first.get("cwd")) if first is not None else None
    if first_cwd is not None:
        fragment["native"] = {"cwd": first_cwd}
    return fragment


def claude_display_name(ctx: NormalizerContext) -> ModelFragment:
    # claude project sessions carry no title at discovery time.
    return {"display_name": None, "display_name_field": None}


def claude_activity(ctx: NormalizerContext) -> ModelFragment:
    transcript = ctx.primary_transcript()
    if transcript is None:
        return {}
    created, activity = _claude_content_timestamps(transcript.path)
    fragment: ModelFragment = {}
    if created:
        fragment[CREATED_AT_CANDIDATES_KEY] = created
    if activity:
        fragment[LAST_ACTIVITY_AT_CANDIDATES_KEY] = activity
    return fragment


def claude_created_at(ctx: NormalizerContext) -> ModelFragment:
    # Mirrors `agentos.claude.session.ClaudeSession.created_timestamp`: the first
    # dialog turn's timestamp (jsonl) or createdAt/lastActivityAt (json). This is a
    # different route from the visible-message summary path, reproduced faithfully.
    transcript = ctx.primary_transcript()
    if transcript is None or not transcript.path.exists():
        return {}
    timestamp = _claude_created_timestamp(transcript.path)
    return {CREATED_AT_CANDIDATES_KEY: [timestamp]} if timestamp is not None else {}


def _claude_content_timestamps(path: Path) -> tuple[list[float], list[float]]:
    try:
        if path.suffix == ".json":
            obj = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
            if not isinstance(obj, dict):
                return [], []
            created = [
                timestamp
                for timestamp in (
                    _raw.coerce_timestamp(obj.get("createdAt")),
                    _raw.coerce_timestamp(obj.get("lastActivityAt")),
                )
                if timestamp is not None
            ]
            activity = list(created)
            return created, activity
        created: list[float] = []
        activity: list[float] = []
        for obj in _raw.iter_jsonl_objects(path):
            for timestamp in _claude_record_timestamps(obj):
                created.append(timestamp)
                activity.append(timestamp)
        return created, activity
    except (OSError, json.JSONDecodeError):
        return [], []


def _claude_record_timestamps(obj: dict[str, object]) -> list[float]:
    timestamps: list[float] = []
    top_level = _raw.coerce_timestamp(obj.get("timestamp"))
    if top_level is not None:
        timestamps.append(top_level)
    snapshot = obj.get("snapshot")
    if isinstance(snapshot, dict):
        snapshot_timestamp = _raw.coerce_timestamp(snapshot.get("timestamp"))
        if snapshot_timestamp is not None:
            timestamps.append(snapshot_timestamp)
    return timestamps


def _claude_created_timestamp(path: Path) -> float | None:
    try:
        if path.suffix == ".jsonl":
            from agentos.agent.extractors.claude_code import (
                extract_dialog_from_claude_code_session,
            )
            from agentos.agent.session_utils import created_timestamp_from_turns

            return created_timestamp_from_turns(
                extract_dialog_from_claude_code_session(path, raw=False)
            )
        if path.suffix == ".json":
            obj = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
            if isinstance(obj, dict):
                return _raw.coerce_timestamp(obj.get("createdAt")) or _raw.coerce_timestamp(
                    obj.get("lastActivityAt")
                )
    except (CliError, OSError, json.JSONDecodeError):
        return None
    return None


CLAUDE_NORMALIZERS = (
    claude_identity,
    claude_cwd,
    claude_display_name,
    claude_activity,
    claude_created_at,
)
