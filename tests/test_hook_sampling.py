# $kw: ^test-agentos-hook-prompt-sampling --from Agentos.Hook --note [DF] verifies that Codex prompt-submission context is preserved through built-in Agentos sampling --supp ^c20260811-25u
from __future__ import annotations

import json
import stat
from pathlib import Path

from agentos.hooks import (
    HookInvocation,
    HookRegistry,
    register_hook_sampling_callbacks,
)
from agentos.testing import AgentosTestEnvironment


def test_prompt_submission_sampling_preserves_codex_context(
    monkeypatch,
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    codex_home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
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

    sample_paths = list(
        (environment.agentos_home / "agent" / "usage-report-hook-samples").glob(
            "*.jsonl"
        )
    )
    assert len(sample_paths) == 1
    assert stat.S_IMODE(sample_paths[0].stat().st_mode) == 0o600
    record = json.loads(sample_paths[0].read_text(encoding="utf-8"))
    assert record["provider"] == "codex"
    assert record["home"] == str(codex_home.resolve())
    assert record["raw_context"] == context
