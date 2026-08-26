"""codex `Raw.Normalizer`s for the index-row target.

Codex index-row metadata is a *multi-source* product: identity and cwd come from
the rollout `session_meta`; the display name (`thread_name`) and an extra activity
timestamp come from the `session_index` entry. The two normalizers emit fragments;
the assembler merges them (cwd rollout-first, display_name from index, activity
coalesced to the max). Timestamp semantics come only from provider artifact content.
"""

from __future__ import annotations

import json
from pathlib import Path

from tarav._core.errors import CliError

from . import _raw
from .context import NormalizerContext
from .fragment import CREATED_AT_CANDIDATES_KEY, LAST_ACTIVITY_AT_CANDIDATES_KEY, ModelFragment


def codex_rollout(ctx: NormalizerContext) -> ModelFragment:
    transcript = ctx.primary_transcript()
    if transcript is None:
        return {}
    meta = ctx.codex_session_meta(transcript.path)
    payload = meta.get("payload") if isinstance(meta, dict) else None
    if not isinstance(payload, dict):
        return {}
    session_id = _raw.string_or_none(payload.get("id"))
    cwd = _raw.string_or_none(payload.get("cwd"))
    fragment: ModelFragment = {"project_path": cwd}
    if session_id is not None:
        fragment["session_id"] = session_id
    if cwd is not None:
        fragment["native"] = {"cwd": cwd}
    return fragment


def codex_rollout_timestamps(ctx: NormalizerContext) -> ModelFragment:
    transcript = ctx.primary_transcript()
    if transcript is None:
        return {}
    created: list[float] = []
    activity: list[float] = []
    meta = ctx.codex_session_meta(transcript.path)
    if isinstance(meta, dict):
        payload = meta.get("payload")
        if isinstance(payload, dict):
            payload_ts = _raw.coerce_timestamp(payload.get("timestamp"))
            if payload_ts is not None:
                created.append(payload_ts)
                activity.append(payload_ts)
        meta_ts = _raw.coerce_timestamp(meta.get("timestamp"))
        if meta_ts is not None:
            created.append(meta_ts)
            activity.append(meta_ts)
    first = ctx.first_jsonl_object(transcript.path)
    if first is not None:
        first_ts = _raw.coerce_timestamp(first.get("timestamp"))
        if first_ts is not None:
            created.append(first_ts)
            activity.append(first_ts)
    for obj in _raw.iter_jsonl_objects(transcript.path):
        timestamp = _raw.coerce_timestamp(obj.get("timestamp"))
        if timestamp is not None:
            activity.append(timestamp)
    fragment: ModelFragment = {}
    if created:
        fragment[CREATED_AT_CANDIDATES_KEY] = created
    if activity:
        fragment[LAST_ACTIVITY_AT_CANDIDATES_KEY] = activity
    return fragment


def codex_index(ctx: NormalizerContext) -> ModelFragment:
    fragment: ModelFragment = {}
    for artifact in ctx.artifacts_by_role("session_index"):
        target_id = _index_target_id(artifact.locator)
        if target_id is None:
            continue
        entry = _find_index_entry(artifact.path, target_id)
        if entry is None:
            continue
        thread_name = _raw.string_or_none(entry.get("thread_name"))
        if thread_name is not None:
            fragment["display_name"] = thread_name
            fragment["display_name_field"] = "thread_name"
            fragment.setdefault("native", {})["thread_name"] = thread_name
        entry_ts = _raw.coerce_timestamp(entry.get("updated_at"))
        if entry_ts is not None:
            fragment.setdefault(LAST_ACTIVITY_AT_CANDIDATES_KEY, []).append(entry_ts)
    return fragment


def _index_target_id(locator: object) -> str | None:
    if not isinstance(locator, dict):
        return None
    match = locator.get("match")
    if not isinstance(match, dict):
        return None
    return _raw.string_or_none(match.get("id"))


def _find_index_entry(path: Path, target_id: str) -> dict[str, object] | None:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict) and _raw.string_or_none(obj.get("id")) == target_id:
                    return obj
    except OSError:
        return None
    return None


def codex_created_at(ctx: NormalizerContext) -> ModelFragment:


    transcript = ctx.primary_transcript()
    if transcript is None or not transcript.path.exists():
        return {}
    timestamp = None
    try:
        from tarav.agent.providers.codex.extractor import extract_dialog_from_codex_rollout
        from tarav.agent.session_utils import created_timestamp_from_turns

        timestamp = created_timestamp_from_turns(
            extract_dialog_from_codex_rollout(transcript.path, raw=False)
        )
    except (CliError, OSError, json.JSONDecodeError):
        timestamp = None
    return {CREATED_AT_CANDIDATES_KEY: [timestamp]} if timestamp is not None else {}


CODEX_NORMALIZERS = (
    codex_rollout,
    codex_rollout_timestamps,
    codex_index,
    codex_created_at,
)
