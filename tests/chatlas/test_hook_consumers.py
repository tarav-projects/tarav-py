from pathlib import Path

import pytest

from agentos.hooks import HookError, HookInvocation, HookRegistry

import agentos.chatlas.hook_consumers as hook_consumers


def test_turn_stop_refresh_is_registered(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    update_calls: list[dict[str, object]] = []
    trust_tiers: list[str] = []

    monkeypatch.setattr(
        hook_consumers,
        "chatlas_update",
        lambda **kwargs: update_calls.append(kwargs) or {"status": "ok"},
    )
    monkeypatch.setattr(
        hook_consumers,
        "set_trust_tier",
        trust_tiers.append,
    )

    registry = HookRegistry()
    hook_consumers.register_chatlas_hook_callbacks(registry)
    invocation = HookInvocation(
        name="agent.turn.stop",
        ctx={"session_id": "session-123", "cwd": str(tmp_path)},
        ctx_type="codex",
    )

    registry.dispatch(invocation)

    assert trust_tiers == ["append"]
    assert update_calls == [
        {
            "providers": ("codex",),
            "session_ids": ("session-123",),
            "start_path": tmp_path,
            "progress": None,
        }
    ]


def test_turn_stop_refresh_ignores_unsupported_context_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    update_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        hook_consumers,
        "chatlas_update",
        lambda **kwargs: update_calls.append(kwargs),
    )

    hook_consumers.update_chatlas_session_from_turn_stop(
        HookInvocation(
            name="agent.turn.stop",
            ctx={"session_id": "session-123"},
            ctx_type="unknown-provider",
        )
    )

    assert update_calls == []


def test_turn_stop_refresh_requires_a_session_id() -> None:
    with pytest.raises(HookError, match="session_id"):
        hook_consumers.update_chatlas_session_from_turn_stop(
            HookInvocation(
                name="agent.turn.stop",
                ctx={},
                ctx_type="codex",
            )
        )
