from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from agentos._core.errors import CliError
from agentos.agent.run_runtime import (
    AgentCommandConfig,
    AgentRunConfig,
    AgentRunDryResult,
    AgentRunResult,
)
from agentos.hooks import AGENTOS_HOOKS_DISABLED_ENV

import agentos.chatlas.chat_index_producer as producer


IDENTITY = "a" * 64


def _source(*turn_ids: str) -> dict[str, object]:
    return {
        "source": {
            "turn_refs": [
                {"turn_ref": {"turn_id": turn_id}}
                for turn_id in turn_ids
            ]
        }
    }


def _show(horizon: str | None) -> dict[str, object]:
    if horizon is None:
        return {"capture": None, "chat_index": {"state": "missing"}}
    return {
        "capture": {"head": {"horizon": {"turn_id": horizon}}},
        "chat_index": {
            "state": "materialized",
            "delta_count": 2,
            "path": "/tmp/chat-index",
        },
    }


@dataclass(frozen=True)
class _Agent:
    provider: str = "codex"
    env: tuple[tuple[str, str], ...] = ()
    calls: list[tuple[AgentCommandConfig, AgentRunConfig, tuple[tuple[str, str], ...]]] = (
        field(default_factory=list, compare=False)
    )

    def run(
        self,
        command_config: AgentCommandConfig,
        run_config: AgentRunConfig,
    ) -> AgentRunResult:
        self.calls.append((command_config, run_config, self.env))
        return AgentRunResult(exit_code=0)

    def run_dry(self, _command_config: AgentCommandConfig) -> AgentRunDryResult:
        return AgentRunDryResult(lines=())


def test_producer_runs_configured_agent_and_verifies_landed_horizon(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    agent = _Agent()
    shows = iter([_show(None), _show("turn-2")])
    monkeypatch.setattr(producer, "chatlas_chat_index_source", lambda **_kwargs: _source("turn-1", "turn-2"))
    monkeypatch.setattr(producer, "chatlas_chat_index_show", lambda **_kwargs: next(shows))
    monkeypatch.setattr(producer, "chatlas_chat_index_audit", lambda **_kwargs: {"ok": True})
    monkeypatch.setattr(
        producer,
        "load_chatlas_run_produce_config",
        lambda **_kwargs: {
            "agent_provider": "codex",
            "profile": "codex-main",
            "model": "gpt-test",
        },
    )
    resolutions: list[dict[str, object]] = []
    monkeypatch.setattr(
        producer,
        "resolve_agent",
        lambda **kwargs: resolutions.append(kwargs) or agent,
    )

    result = producer.maintain_chat_index_with_agent(
        identity_hash=IDENTITY,
        chatlas_root=tmp_path,
    )

    assert result == {
        "status": "ok",
        "identity_hash": IDENTITY,
        "skipped": False,
        "target_turn_id": "turn-2",
        "delta_count": 2,
        "surface_path": "/tmp/chat-index",
    }
    assert resolutions == [
        {
            "provider": "codex",
            "profile": "codex-main",
            "start_path": tmp_path,
        }
    ]
    command, run, env = agent.calls[0]
    assert command.prompt == producer.CAPTURE_PROMPT.format(identity_hash=IDENTITY)
    assert command.model == "gpt-test"
    assert command.interaction_mode == "non_interactive"
    assert run == AgentRunConfig(cwd=tmp_path, process_mode="capture")
    assert dict(env)[AGENTOS_HOOKS_DISABLED_ENV] == "1"


def test_producer_skips_an_audited_current_surface(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(producer, "chatlas_chat_index_source", lambda **_kwargs: _source("turn-1"))
    monkeypatch.setattr(producer, "chatlas_chat_index_show", lambda **_kwargs: _show("turn-1"))
    monkeypatch.setattr(producer, "chatlas_chat_index_audit", lambda **_kwargs: {"ok": True})
    monkeypatch.setattr(
        producer,
        "resolve_agent",
        lambda **_kwargs: pytest.fail("current capture must not spawn an agent"),
    )

    result = producer.maintain_chat_index_with_agent(
        identity_hash=IDENTITY,
        chatlas_root=tmp_path,
    )

    assert result["skipped"] is True
    assert result["reason"] == "current"


def test_producer_rejects_success_without_requested_horizon(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    agent = _Agent()
    shows = iter([_show(None), _show("turn-1")])
    monkeypatch.setattr(producer, "chatlas_chat_index_source", lambda **_kwargs: _source("turn-1", "turn-2"))
    monkeypatch.setattr(producer, "chatlas_chat_index_show", lambda **_kwargs: next(shows))
    monkeypatch.setattr(
        producer,
        "load_chatlas_run_produce_config",
        lambda **_kwargs: {"agent_provider": "codex", "profile": "codex-main"},
    )
    monkeypatch.setattr(producer, "resolve_agent", lambda **_kwargs: agent)

    with pytest.raises(CliError, match="without materializing"):
        producer.maintain_chat_index_with_agent(
            identity_hash=IDENTITY,
            chatlas_root=tmp_path,
        )
