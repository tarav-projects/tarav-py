# $kw: ^test-agentos-hook-prompt-sampling --from Agentos.Hook --note [DF] verifies that Codex prompt-submission context is preserved through built-in Agentos sampling --supp ^c20260811-25u
from __future__ import annotations

import json
import stat
from pathlib import Path

from tarav.hooks import (
    HookInvocation,
    HookRegistry,
    append_hook_context_sample,
    hook_context_sample_log_path,
    register_hook_sampling_callbacks,
)
from tarav.testing import TaravTestEnvironment


def test_prompt_submission_sampling_preserves_opaque_context(
    monkeypatch, tmp_path: Path
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    registry = HookRegistry()
    register_hook_sampling_callbacks(registry)
    context = {
        "hook_event_name": "UserPromptSubmit",
        "session_id": "session-123",
        "turn_id": "turn-456",
        "prompt": "peek at this submission",
    }

    registry.dispatch(
        HookInvocation(
            name="agent.prompt.submit",
            ctx=context,
            ctx_type="codex",
        )
    )

    sample_path = hook_context_sample_log_path()
    assert sample_path == environment.tarav_home / "hooks" / "context-samples.jsonl"
    assert stat.S_IMODE(sample_path.stat().st_mode) == 0o600
    record = json.loads(sample_path.read_text(encoding="utf-8"))
    assert record["hook_name"] == "agent.prompt.submit"
    assert record["ctx_type"] == "codex"
    assert record["ctx"] == context
    assert "provider" not in record
    assert "home" not in record


def test_hook_context_sampling_retention_is_bounded_across_time(
    monkeypatch, tmp_path: Path
) -> None:
    environment = TaravTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)

    for number in range(5):
        append_hook_context_sample(
            HookInvocation(
                name="agent.prompt.submit",
                ctx={"number": number},
                ctx_type="codex",
            ),
            max_records=3,
        )

    records = [
        json.loads(line)
        for line in hook_context_sample_log_path()
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [record["ctx"]["number"] for record in records] == [2, 3, 4]
