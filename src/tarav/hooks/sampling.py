# $kw: ^agentos-hook-prompt-sampling --from Agentos.Hook --from Agentos.Hook.Invocation --note [DC] prompt-submission callbacks keep an independent bounded private store of opaque hook invocations --supp ^c20260811-5u ^c20260811-12u ^c20260811-25u ^c20260811-47u
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
from collections.abc import Mapping

from tarav._core.clock import iso_z
from tarav._core.errors import CliError
from tarav._core.project import tarav_home_dir

from .model import HookInvocation
from .registry import HookRegistry


HOOK_CONTEXT_SAMPLE_CLASS = "agentos.hook-context-sample"
HOOK_CONTEXT_SAMPLE_SCHEMA_VERSION = 1
DEFAULT_HOOK_CONTEXT_SAMPLE_MAX_RECORDS = 50


def hook_context_sample_log_path() -> Path:
    return tarav_home_dir() / "hooks" / "context-samples.jsonl"


def append_hook_context_sample(
    invocation: HookInvocation,
    *,
    max_records: int = DEFAULT_HOOK_CONTEXT_SAMPLE_MAX_RECORDS,
) -> Path:
    if not isinstance(invocation, HookInvocation):
        raise CliError("hook context sampling requires a HookInvocation")
    if max_records <= 0:
        raise CliError("hook context sample max_records must be positive")

    record = {
        "schema_version": HOOK_CONTEXT_SAMPLE_SCHEMA_VERSION,
        "class": HOOK_CONTEXT_SAMPLE_CLASS,
        "recorded_at": iso_z(datetime.datetime.now(tz=datetime.UTC)),
        "hook_name": invocation.name,
        "ctx_type": invocation.ctx_type,
        "ctx": dict(invocation.ctx),
    }
    try:
        line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
    except TypeError as exc:
        raise CliError(f"hook context sample is not JSON serializable: {exc}") from exc

    path = hook_context_sample_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
    os.chmod(path, 0o600)
    _trim_hook_context_samples(
        path,
        hook_name=invocation.name,
        ctx_type=invocation.ctx_type,
        max_records=max_records,
    )
    return path


def register_hook_sampling_callbacks(registry: HookRegistry) -> None:
    """Register bounded development sampling for prompt-submission contexts."""

    registry.register(
        "agent.prompt.submit",
        _sample_prompt_submission,
        callback_id="agentos.hooks.sample-prompt-submission",
    )


def _sample_prompt_submission(invocation: HookInvocation) -> None:
    append_hook_context_sample(invocation)


def _trim_hook_context_samples(
    path: Path,
    *,
    hook_name: str,
    ctx_type: str | None,
    max_records: int,
) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    matching_indexes: list[int] = []
    for index, line in enumerate(lines):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, Mapping) and _sample_matches(
            record,
            hook_name=hook_name,
            ctx_type=ctx_type,
        ):
            matching_indexes.append(index)
    excess = len(matching_indexes) - max_records
    if excess <= 0:
        return
    remove_indexes = set(matching_indexes[:excess])
    path.write_text(
        "".join(
            f"{line}\n"
            for index, line in enumerate(lines)
            if index not in remove_indexes
        ),
        encoding="utf-8",
    )
    os.chmod(path, 0o600)


def _sample_matches(
    record: Mapping[str, object],
    *,
    hook_name: str,
    ctx_type: str | None,
) -> bool:
    return (
        record.get("schema_version") == HOOK_CONTEXT_SAMPLE_SCHEMA_VERSION
        and record.get("class") == HOOK_CONTEXT_SAMPLE_CLASS
        and record.get("hook_name") == hook_name
        and record.get("ctx_type") == ctx_type
    )


__all__ = [
    "DEFAULT_HOOK_CONTEXT_SAMPLE_MAX_RECORDS",
    "HOOK_CONTEXT_SAMPLE_CLASS",
    "HOOK_CONTEXT_SAMPLE_SCHEMA_VERSION",
    "append_hook_context_sample",
    "hook_context_sample_log_path",
    "register_hook_sampling_callbacks",
]
